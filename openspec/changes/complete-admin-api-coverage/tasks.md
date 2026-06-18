## 1. 观测查询 HTTP API（专用端点）

- [ ] 1.1 [测试] `tests/integration/test_observability_admin_api.py` 新增守门测试：`test_observability_routes_exist`（`GET /admin/observability/traces` 返回非 404）→ 运行必须红
- [ ] 1.2 [实现] 新建 `src/fleetent/platform/observability_management/observability_admin_api.py`，router prefix `/admin/observability`，session token + `_require_admin` 鉴权：
  - `GET /traces` — 包装 `observability.query_trace_events(TraceQuery(...))`，query 参数：run_id/user_id/agent/session_id/tenant_id/event_type/since/until/limit
  - `GET /usage` — 包装 `observability.get_usage_summary(UsageQuery(...))`
  - `GET /performance` — 包装 `observability.get_performance_summary(...)`
- [ ] 1.3 [实现] `server.py` 注册 `observability_admin_api.router`
- [ ] 1.4 [测试] 补充完整场景测试并见绿：`test_traces_filter_by_run_id`、`test_traces_multi_filter`、`test_usage_by_agent`、`test_performance_metrics`、`test_non_admin_returns_403`
- [ ] 1.5 [验证] `uv run pytest tests/integration/test_observability_admin_api.py -x -q` → 全绿

## 2. 接通 /admin/stats/* 占位桩

- [ ] 2.1 [测试] `tests/integration/test_stats_admin_api.py` 新增/改 `test_stats_overview_uses_real_traces`：构造真实 trace + approvals，断言 overview 返回非空真实聚合（不是空集）→ 运行必须红（当前桩返回空）
- [ ] 2.2 [实现] `agent_statistics/stats_admin_api.py` 把 `fetch_traces`/`fetch_approvals`/`pricing_table` 接到真实数据源（`observability` 公共 API + model-pricing 表）；保留 `agent_allowed_tools` 经 agent_store 的 bridge
- [ ] 2.3 [实现] 同步更新原本断言"返回空集"的旧测试为真实数据预期
- [ ] 2.4 [验证] 核对 viewer per-user mask 路径（`MASK_PER_USER_FOR_VIEWER`）在接真实数据后仍生效（OQ2）
- [ ] 2.5 [验证] `uv run pytest tests/integration/test_stats_admin_api.py -x -q` → 全绿

## 3. 服务账号创建 + key 轮换 HTTP API

- [ ] 3.1 [测试] `tests/integration/test_service_principal_api.py` 新增 `test_create_service_principal_returns_key_once`、`test_rotate_key_revokes_and_issues`、`test_rotate_unknown_user_404`、`test_non_admin_403` → 运行必须红
- [ ] 3.2 [实现] `user_management/user_admin_api.py`（或新建 router）新增：
  - `POST /admin/service-principals` → `user_store.create_user(name)`，返回 `api_key_plaintext_once`
  - `POST /admin/users/{user_id}/rotate-key` → `user_store.rotate_key(user_id)`，返回 `api_key_plaintext_once`；user 不存在 404
  - 两者均 `_require_admin` + `audit_log.write_audit`
- [ ] 3.3 [验证] `uv run pytest tests/integration/test_service_principal_api.py -x -q` → 全绿

## 4. default-agent 控制面化（最高风险，最后做）

- [ ] 4.1 [测试] `tests/integration/test_default_agent_admin.py` 新增 `test_default_agent_routes_exist` → 红
- [ ] 4.2 [实现] Alembic 迁移：`agent_admin_state` 加 `is_default` 列（**迁移版本号不要硬编码，apply 时跑 `uv run alembic heads` 取当前 head 续号**）；代码层保证每 tenant 至多一个 default
- [ ] 4.3 [测试] `tests/integration/` 新增 `test_set_default_clears_previous`、`test_materialize_emits_bindings_default`（默认 agent 的 materialize 产物含 `bindings.default: true`）→ 红
- [ ] 4.4 [实现] `agent_management_console/agent_admin_api.py` 新增 `PUT /admin/agents/{name}/default`、`DELETE /admin/agents/default`（admin 鉴权 + 审计）；store 层加 set/clear default
- [ ] 4.5 [实现] `agent_lifecycle/materialize.py`：对 `is_default` 的 agent 在产出 agent.yaml 时写 `bindings.default: true`
- [ ] 4.6 [测试] `tests/integration/test_default_agent_backfill.py` 新增 `test_existing_file_default_backfilled`：存量 agent.yaml 有 `bindings.default: true` 时，迁移/回填后 materialize 产物的 default 与回填前一致 → 红
- [ ] 4.7 [实现] 一次性回填：把现有 agent.yaml 的 `bindings.default` 标记读入 `is_default`（迁移内或 `scripts/upgrade.py`）
- [ ] 4.8 [验证] `uv run pytest tests/integration/test_default_agent_admin.py tests/integration/test_default_agent_backfill.py -x -q` → 全绿

## 5. 收尾验证

- [ ] 5.1 [验证] `make test-pr` → 全绿（unit + layer boundaries + ruff）
- [ ] 5.2 [验证] `uv run pytest tests/integration -q` → 对照 main 基线无新增失败
- [ ] 5.3 [验证] `make test-unit-ci` → unit 覆盖率 ≥ 76%
- [ ] 5.4 [验证] `uv run alembic upgrade head` 后 `uv run alembic heads` 确认单一 head（含本 change 的 is_default 迁移）
