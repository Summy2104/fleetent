## Why

platform UI 的会话治理（sessions）功能前后端虽接线完整（前端页面 / i18n / RBAC / 9 个 endpoint / 单测全有），但生产环境实质不可用，属于 build-but-unwired 半成品，且与 `platform → node → agent` 单向解耦契约冲突：

- **列表恒空**：管理库 `session_meta` 表的唯一写入入口 `session_admin_store.upsert_meta` 在 `src/` 里零调用方（只有 `tests/` 调），生产从不登记会话，故 `GET /admin/sessions` 永远返回空，连选中会话的入口都没有。
- **managed 拿不到数据**：解耦拓扑下 platform 与 agent 不共享文件系统，且 `agent_transport` 没有任何跨 node session 通道，`load_transcript / inject / clear / reset` 读写的是 platform 进程本地不存在的 session 文件，静默无效。
- **统计是假数据**：`session_stats` 注释明写 placeholder，恒返回 0；`im_deliver` seam 是 no-op，IM 来源会话的 inject 不会回投。

继续维护这块代码只会让"看起来能用、实则空转、还误导测试"的死重不断累积。决定整体移除。

## What Changes

- **BREAKING**：移除 `/admin/sessions/*` 共 9 个会话治理 endpoint（list / detail / takeover / release / inject / force-end / clear / reset / bulk）。
- 删除后端整包 `platform/chat_management/`（`chat_admin_api.py` + `session_admin_store.py` + 未接线的 `transcript_export.py` + `__init__.py`），并解除 `server.py` 对它的 import、seam 注入、`include_router` 接线。
- 删除前端 sessions feature（`features/sessions/` 整目录、路由、导航项、`i18n` 的 `nav.sessions` + `sessions.*` 词条、路由测试断言）。
- 新增 Alembic 迁移 drop 管理库 `session_meta` 表及 `idx_session_meta_origin` 索引（该表生产恒空，零数据损失）。
- 清理 guardrail 测试 `_CONTROL_FACE_PREFIXES` 中的 `fleetent.platform.chat_management` 项，及 `test_platform_admin_api_unit.py` 中 chat_admin_api 相关用例。

**明确不动（同名但属于其它 capability）**：

- `GET /admin/stats/sessions/{session_id}/trace`（`agent_statistics`，走 observability traces 库，被 `features/stats/` 消费）——保留。
- agent 侧 `session/` 模块（`manager.py` / `index.py`，per-agent `agent_state.db` 的 `sessions` 表，core runtime）——保留。`manager.py` 的 admin 专用方法（`inject_message` 等）在 apply 阶段逐个 grep 确认无其它消费方后才清理，本 change 不武断删。

## Capabilities

### New Capabilities

无。

### Modified Capabilities

- `session-admin-console`: 移除整个后端会话治理 capability（list / replay / takeover / force-end-clear-reset / batch / export / 权限审计全部 REMOVED）。
- `session-admin-ui`: 移除整个前端 React SPA sessions capability（原生 sessions 视图、治理操作、viewer 只读全部 REMOVED）。

> `session-metadata-index`（agent 侧 `agent_state.db` 的 `sessions` 表）**不在本 change 范围**——它是 core runtime，与管理库 `session_meta` 治理表是两个不同的东西，不得触碰。

## Impact

- **API**：移除 `/admin/sessions/*` 9 个 endpoint（前端是唯一消费方，无其它下游）。
- **代码**：删除 `src/fleetent/platform/chat_management/`（整包）；改 `src/fleetent/server.py`（解除接线）；删除 `frontend/src/features/sessions/`，改 `frontend/src/app/{routes.tsx,nav.ts,routes.test.tsx}`、`frontend/src/i18n/messages.ts`。
- **数据库**：新增迁移（head 113 → 114）drop `session_meta` + 索引。owned tables 减一。
- **测试**：删除 `tests/integration/test_chat_admin_api.py`、`tests/integration/test_session_admin_store.py`、`tests/unit/test_transcript_export.py`；改 `tests/unit/test_server_lifespan_and_wiring.py`（去 sessions seam 断言）、`tests/unit/test_platform_admin_api_unit.py`（去 chat_admin_api 用例）、`tests/unit/test_module_dependency_guardrails.py`（去 `chat_management` 前缀项）。
- **依赖**：`server.py` 不再依赖 `chat_management`；无 re-export shim 需求（整 feature 退场，无下游）。
- **config namespace**：无。
