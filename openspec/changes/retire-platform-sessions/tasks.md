> 删除型 change 的 TDD 语义（见 design D5）：先把"断言该功能存在"的测试改成反映移除后的期望状态并跑绿（基线），再删实现使代码与之一致并跑绿。每步用最窄命令 `uv run pytest <file>::<test> -x -q`。

## 1. 后端：解除 server.py 对 chat_admin_api 的接线

- [ ] 1.1 改 `tests/unit/test_server_lifespan_and_wiring.py`：删去断言 `chat_admin_api.load_transcript` / `clear_session` / `inject` / `reset_session` 被接成 callable 的用例（`:209`、`:253` 附近）；跑该文件确认绿
- [ ] 1.2 删 `src/fleetent/server.py` 的 `:41` import、`:234-244` 四个 seam 注入、`:282` `include_router(chat_admin_api.router)`；跑 `test_server_lifespan_and_wiring.py` 全文件确认绿

## 2. 后端：删除 chat_management 整包及其测试

- [ ] 2.1 删除测试文件 `tests/integration/test_chat_admin_api.py`、`tests/integration/test_session_admin_store.py`、`tests/unit/test_transcript_export.py`
- [ ] 2.2 改 `tests/unit/test_platform_admin_api_unit.py`：删去 `from ... import chat_admin_api`（`:16`）及所有 chat_admin_api / sessions 相关用例（`:459` 起的 sessions fixture 与断言）；跑该文件确认绿
- [ ] 2.3 改 `tests/unit/test_module_dependency_guardrails.py`：从 `_CONTROL_FACE_PREFIXES`（`:368`）删去 `"fleetent.platform.chat_management"` 项；跑该文件确认绿
- [ ] 2.4 删除 `src/fleetent/platform/chat_management/` 整包（`chat_admin_api.py`、`session_admin_store.py`、`transcript_export.py`、`__init__.py`）；跑 `make test-unit` 确认无新增失败、无 collect error

## 3. 数据库：drop 恒空的 session_meta 表

- [ ] 3.1 写 integration 测试：Alembic upgrade 到 head 后管理库不存在 `session_meta` 表（先跑见红——当前 head 113 仍有该表）
- [ ] 3.2 复核 `ls migrations/versions/ | tail` 确认 head=113，新增 `migrations/versions/114_drop_session_meta.py`：`upgrade` drop index `idx_session_meta_origin` + drop table `session_meta`，`downgrade` 按 022 当前列形态重建空表；跑 3.1 测试确认绿

## 4. 前端：删除 sessions feature

- [ ] 4.1 改 `frontend/src/app/routes.test.tsx`：删去 sessions 路由（`:281-293`）与 `nav.sessions` 链接（`:165`）断言；跑前端测试确认绿
- [ ] 4.2 删除 `frontend/src/features/sessions/` 整目录（page / api / 测试）
- [ ] 4.3 改 `frontend/src/app/routes.tsx`（去 `:22` import + `:324` `<Route path="/sessions">`）、`frontend/src/app/nav.ts`（去 `:40` 导航项）
- [ ] 4.4 删 `frontend/src/i18n/messages.ts` 的 `nav.sessions`（中英）与全部 `sessions.*` 词条（中英约 80 条）
- [ ] 4.5 跑前端测试 + `tsc` 类型检查确认全绿、无悬空引用

## 5. 收尾验证

- [ ] 5.1 对 `src/fleetent/session/manager.py` 的 admin 候选方法（`inject_message`、及评估 `clear`/`reset`）逐个 `grep -rn` 全仓核查：无 admin 之外消费方者删除并跑相关测试，有任何疑问即保留（design D4）
- [ ] 5.2 全仓 `grep -rn "admin/sessions"`（排除 `agent_statistics` 的 stats trace）确认无残留引用；确认 `GET /admin/stats/sessions/{id}/trace` 与 `features/stats/` 完好
- [ ] 5.3 跑 `make test-pr` + `make test-integration-ci` 全绿
- [ ] 5.4 烟测 agent 验证基线：无 platform 环境下 `uv run fleetent "hello"` / `fleetent agent run` 对话正常
