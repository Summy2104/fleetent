## Context

`server.py` 在 lifespan 里把 `run_stream`（agent 运行时）注入给 `chat_admin_api.run_playground`，使 platform 进程能在内部执行 agent loop。这是 `platform-control-plane` spec 的唯一现存违规：spec 声明 platform 不执行 agent loop，但 playground 作为隐性豁免一直存在。

`chat_admin_api` 里有两块逻辑共用同一个文件：

| 路由前缀 | 功能 | 处置 |
|---|---|---|
| `/admin/chat/*` | playground（7 条端点） | **删除** |
| `/admin/sessions/*` | 真实会话治理（7 条端点） | **保留** |

两块共享 `load_transcript` / `clear_session` / `inject` / `reset_session` 四个 seam，这些 seam 由 server.py lifespan 统一注入。

## Goals / Non-Goals

**Goals:**
- 删除 `server.py` 对 `fleetent.runtime` 的所有 import，使 platform 进程零 runtime 依赖
- 删除 `/admin/chat/*` 7 条 playground 路由及其专属逻辑
- 保留 `/admin/sessions/*` 会话治理路由功能完整

**Non-Goals:**
- 不提供 playground 替代品（用 TUI 或 IM 渠道替代，不在本 change 范围）
- 不改变 `/admin/sessions/*` 任何行为
- 不删除 `chat_admin_api` 中与 playground 无关的 session 治理代码
- 不改动 agent 侧 `/ws` 服务端（TUI gateway 不受影响）

## Decisions

### 决策 1：`loop` 变量保留，seam 注入保留

`asyncio.get_running_loop()` 在 lifespan 里被 playground 和 session 治理 seam 共用（`clear_session` / `inject` / `reset_session` 都用 `run_coroutine_threadsafe(…, loop)`）。删 playground 后，`loop` 仍被 session seam 使用，不能一并删除。

### 决策 2：`maint` scheduler 整体删除

`server.py` 的 `AsyncIOScheduler` 只有一个 job：`playground_retention`。删 playground 后调度器没有任何其他用途，整体移除，无需保留骨架。

### 决策 3：`approval_resume` import 不在本 change 处理

`server.py` lifespan 里有 `from fleetent.runtime.approval_resume import reconcile_expired_approvals`。此 import 服务于审批过期处理，与 playground 无关，本 change 不触碰，留给后续 runtime import 清零专项处理（若需要）。

> **注**：该 import 是目前 server.py 中除 `run_stream` 之外仍存在的 runtime import，删完 `run_stream` 后 server.py 对 runtime 的依赖还有这一处，本 change **仅** 声明"删 `run_stream`"，不承诺"server.py 零 runtime import"。

### 决策 4：playground session 历史数据不清理

已有 `origin=playground` 的 session 记录留在 DB，不做数据迁移。retention 调度器删除后这些记录不会自动清理，但也不影响功能（session 治理 list 接口可按 `origin` 过滤）。

## Risks / Trade-offs

- **[风险] 有用户依赖 playground** → 缓解：playground 仅限 admin 账号，生产环境用 TUI 或 IM 渠道替代；BREAKING 变更在 proposal 中已明确标注
- **[风险] `approval_resume` import 遗留** → 缓解：本 change 不声明"server.py 零 runtime import"，只声明"删 run_stream"；后续专项 change 处理

## Migration Plan

1. 删 `server.py` 中 `_pg_run` 函数、`run_stream` import、`chat_admin_api.run_playground` wiring、`maint` scheduler、`_run_playground_retention`
2. 删 `chat_admin_api.py` 中 `/admin/chat/*` 7 条路由、`run_playground` / `run_playground_stream` / `purge_expired_playground` seam 定义、`_require_own_playground` / `_require_agent` helper
3. 删对应单测（`test_chat_playground*` 等 playground 专属测试）
4. 更新 `platform-control-plane` spec：移除 playground 豁免注记，更新声明为"server.py 不 import run_stream"
5. 归档 `chat-playground` spec

无需 DB 迁移，无需部署协调，单次提交即可上线。
