# Tasks

## 1. 测试先行（见红）

- [x] 1.1 在 `tests/unit/` 为 `cron_scheduler._resolve_cron_principal` 的 **standalone（未注入 resolver）** 路径写单测：fixture 确保 `cron_scheduler._principal_resolver is None`；带平台 IM `origin` + 真实 user_id → 返回 `Principal(user_id, "default")`；无 IM origin 的非 default user_id → 返回 `None`；`user_id="system"` → `SYSTEM_PRINCIPAL`、`="default"` → `Principal("default","default")`。断言整个过程**不调用 `user_store`**（如 `monkeypatch` 一个会抛异常的 `user_store.get_by_id` 占位，验证它从未被触发）。
- [x] 1.2 写回归单测（复现 dev 事故）：standalone 未注入 resolver，`DATABASE_URL=""`（或指向不可打开路径）时，带 IM 身份的任务仍解析出 `Principal` 而非 `None`——即 fire 不因空/错 `DATABASE_URL` 被跳过。
- [x] 1.3 为 **platform（已注入 resolver）** 路径写单测：调用 `set_principal_resolver` 装入一个桩 resolver；`_resolve_cron_principal` 委派给它；并对"等价复刻"的注入实现单独测四分支（blocked→`None`、正常→`Principal(u.id,u.tenant_id)`、无行但有 IM origin→信任、无行无 origin→`None`）。用例间复位 `_principal_resolver=None`。
- [x] 1.4 在 `tests/unit/test_module_dependency_guardrails.py` 增断言：`cron_scheduler` 源码 / 已导入模块不依赖 `fleetent.user_store`（固化 spec「fire 路径不碰 user_store」，防回潮）。
- [x] 1.5 运行上述用例（最窄命令）确认**见红**。

## 2. 实现（见绿）

- [x] 2.1 在 `cron_scheduler` 增模块级 `_principal_resolver: Callable[[dict], Principal | None] | None = None` 与 `set_principal_resolver(resolver)`（对齐 `user_store.set_api_key_resolver` 形态，含 docstring 说明 standalone 留 None）。
- [x] 2.2 重写 `_resolve_cron_principal`：保留 `system`/`default` 短路在最前；`_principal_resolver is None` → 走 origin 信任 / fail-closed，**不碰 DB**；否则 `return _principal_resolver(task)`。移除 `import fleetent.user_store`（及仅为旧 except 服务的 `sqlite3` import）。每步跑 1.x 用例见绿。
- [x] 2.3 在 `server.py` lifespan 增注入闭包 `_cron_principal_recheck(task)`（内部 `user_store.get_by_id` + blocked/deleted + origin 兜底，等价复刻原逻辑）并 `cron_scheduler.set_principal_resolver(_cron_principal_recheck)`，与现有三处注入并列。跑 1.3 见绿。

## 3. 收尾验证

- [x] 3.1 跑受影响 unit 层（`tests/unit/test_module_dependency_guardrails.py` + cron_scheduler 相关用例）确认无新增失败。
- [x] 3.2 `make test-pr`（unit + 层边界 + 改动文件 ruff）全绿；`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过。
- [x] 3.3 标记所有 checkbox 为 `[x]`，准备 archive。
