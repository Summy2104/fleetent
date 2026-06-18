## Why

admin 控制台的「Chat 试验场（playground）」在 platform 进程内直接调用 `run_stream`（agent 运行时），是目前 platform→runtime 唯一剩余的耦合点，与 `platform-control-plane` 的"platform 不执行 agent loop"原则直接冲突。目标架构下 platform 是纯控制面，agent 执行只发生在独立的 `fleetent agent run` 进程里；playground 没有理由成为例外。

## What Changes

- **删除 playground 执行路由**：移除 `chat_admin_api` 中的 7 条 `/admin/chat/*` 端点（`/chat/start`、`/chat/sessions`、`DELETE /chat/{id}`、`/chat/{id}/message`、`/chat/{id}/stream`、`/chat/{id}/pin`、`/chat/{id}/export`）。
- **删除 playground seam**：移除 `chat_admin_api` 中的 `run_playground`、`run_playground_stream`、`purge_expired_playground` seam 定义及 `_require_own_playground`、`_require_agent` helper。
- **断开 server.py 中的 runtime 耦合**：删除 `from fleetent.runtime import run_stream`、`_pg_run` 函数（约 40 行）、`chat_admin_api.run_playground = _pg_run` wiring、`asyncio.get_running_loop()` 调用（若仅 playground 使用）。
- **删除 playground 维护调度器**：删除 `server.py` 中的 `maint = AsyncIOScheduler()`（只有一个 job：`playground_retention`）和 `_run_playground_retention` 函数。
- **保留会话治理路由**：`/admin/sessions/*` 7 条端点及其 seam（`load_transcript`、`clear_session`、`inject`、`reset_session`）完整保留。
- **BREAKING**：`/admin/chat/*` 全部端点下线；`fleetent-admin` 无等价替代（运维测试 agent 改用 TUI 或 IM 渠道）。
- 清理 playground 相关单测。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `chat-playground`：整个 capability 下线，spec 标记为 archived/removed。
- `platform-control-plane`：移除"playground 作为 in-process runtime 例外"的豁免注记，声明 server.py 零 runtime import。

## Impact

**owning package**：`platform`（`src/fleetent/platform/chat_management/chat_admin_api.py`）+ 入口（`src/fleetent/server.py`）。

**public API surface（移除）**：`/admin/chat/start`、`/admin/chat/sessions`、`DELETE /admin/chat/{session_id}`、`/admin/chat/{session_id}/message`、`/admin/chat/{session_id}/stream`、`/admin/chat/{session_id}/pin`、`/admin/chat/{session_id}/export`。

**public API surface（保留）**：`/admin/sessions/*` 全部端点不变。

**owned tables**：无（playground 用的是普通 session 表，origin=playground 过滤；删路由后数据不会新增，旧 playground session 历史数据留存无害）。

**config namespace**：无新增/删除配置项。

**cross-module dependencies**：删除后 `server.py` 对 `fleetent.runtime` 的 import 归零，platform/runtime 边界清洁。

**migration / shim plan**：无持久层改动，无迁移。`run_playground` seam 在 `chat_admin_api` 内无外部调用者（仅 server.py 注入），删后无需 shim。
