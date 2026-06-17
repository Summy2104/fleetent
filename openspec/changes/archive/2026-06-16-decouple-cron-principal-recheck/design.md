## Context

`cron_scheduler._resolve_cron_principal(task)` 在每次 fire 时解析「以谁的身份跑这个定时任务」，
并顺带做创建者撤权复核。当前实现直接调 `user_store.get_by_id(user_id)`：

```python
try:
    u = user_store.get_by_id(user_id)          # 打开 management 库查 users 表
except sqlite3.OperationalError as exc:
    if "no such table" in str(exc):            # 仅此一种异常被当作 standalone
        return Principal(user_id, "default")
    return None                                 # 其余 → fail-closed
except Exception:                               # ValueError 等 → fail-closed
    return None
```

`user_store._db()` = `create_database(Settings().database_url)`。`Settings.database_url` 默认是
合法 sqlite 路径，故本地 standalone 走 `no such table` 兜底能跑；但 `DATABASE_URL=""`（空串）时
`create_database("")` 因空 scheme 抛 `ValueError`，落入 `except Exception` → fail-closed → 跳过 fire。
根因不是空串本身，而是 **fire-time 身份解析这条路径未像 `authenticate` 那样做注入解耦**，让 agent
runtime 隐式依赖 platform 的 management 库。

既有注入范式（`server.py` lifespan，standalone 的 `agent_app` 路径不会执行）：

```python
user_store.set_api_key_resolver(_resolve_api_key)
connectors.set_provider(vault_provider.get_credential)
set_im_identity_resolver(_resolve_im_identity)
```

## Goals / Non-Goals

**Goals:**
- `cron_scheduler` fire-time 路径不再 import/调用 `user_store`、不再打开 management 库。
- standalone（无注入）信任 task `origin` 的已认证 IM 身份；空/错 `DATABASE_URL` 不影响 fire。
- platform（注入 resolver）保持 blocked/deleted 撤权复核语义不变。
- 复用既有 `set_*_resolver` 注入范式，零新概念。

**Non-Goals:**
- 不改 `schedule_store`、调度触发、投递契约、schedule 工具。
- 不改 `users` 表 schema 或 platform 撤权逻辑本身（只是改由注入提供）。
- 不引入新配置项 / 不动 `DATABASE_URL` 的默认值。

## Decisions

1. **注入缝放在 `cron_scheduler`**：模块级 `_principal_resolver: Callable[[dict], Principal | None] | None = None`
   + `set_principal_resolver(resolver)`。与 `user_store.set_api_key_resolver` 同形。
2. **`_resolve_cron_principal` 行为分流**：
   - `user_id == "system"` → `SYSTEM_PRINCIPAL`；`== "default"` → `Principal("default","default")`（不变，短路在最前）。
   - `_principal_resolver is None`（standalone）：读 `task["origin"]`，是 dict 且含 `platform` → `Principal(user_id, "default")`；否则 `None`（fail-closed）。**不碰任何 DB。**
   - `_principal_resolver is not None`（platform）：`return _principal_resolver(task)`。
3. **查库逻辑迁到 platform 注入闭包**（`server.py`）：闭包内 `user_store.get_by_id` + blocked/deleted + origin 兜底，逻辑等价于今天 `_resolve_cron_principal` 里 `u is not None` 之后那段。
4. **移除 `cron_scheduler` 顶部 `import fleetent.user_store`**（fire 路径不再需要）；`sqlite3` import 若仅为该 except 也一并清理。
5. **注入点**：`server.py` lifespan 增一行 `cron_scheduler.set_principal_resolver(_cron_principal_recheck)`，与现有三处注入并列。

## Risks / Trade-offs

- **测试可能 patch `_resolve_cron_principal` 内部对 `user_store` 的调用**：重写后该调用消失，需同步更新相关单测（改为断言 standalone 信任路径 / 注入路径）。
- **platform 模式行为等价性**：注入闭包必须严格复刻原 `blocked → None / 正常 → Principal(u.id,u.tenant_id) / 无行但有 IM origin → 信任 / 否则 None` 四分支，避免回归。以单测锁定。
- **全局可变状态**：`_principal_resolver` 是模块级单例，与既有 `_api_key_resolver` 同类；测试需在用例间复位（fixture 清 `None`），否则跨用例串味。
- **guardrail 收紧**：spec 要求 cron 不 import user_store；若 `module-dependency-guardrails` 测试可表达"cron 不依赖 user_store"，可加一条断言固化，防回潮（可选，纳入 tasks）。
