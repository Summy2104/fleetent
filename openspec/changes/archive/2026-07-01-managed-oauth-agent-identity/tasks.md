# Tasks — managed-oauth-agent-identity

> 每个实现 task 严格 TDD：先写测试跑到见红，再写实现跑到见绿。测试任务在对应实现任务之前。

## P1 — 平台侧 client_secret 按 agent 名字解析（name→id 映射 + 全局兜底）

- [x] 1.1 (test) unit：`tests/unit/test_mcp_oauth_service_secret_resolve.py` —
  - `_resolve_client_secret` 把**原始 agent_id 串**透传给注入 resolver（名字如 `"bi-intern"` 不被 `int()` 门挡掉、原样传入）；
  - `client_secret_env` 为空 → 返回 `""`（不调 resolver）；
  - 未注入 resolver → 返回 `""`。
  用 fake resolver 捕获收到的实参。跑 `uv run pytest tests/unit/test_mcp_oauth_service_secret_resolve.py -x -q` 见红。
- [x] 1.2 (impl) `platform/connector_management/mcp_oauth_service.py`：
  - `_client_secret_resolver` 契约 `(int|None,str)→(str|None,str)`（`set_client_secret_resolver` 类型同步）；
  - `_resolve_client_secret` 改为 `return _client_secret_resolver(agent_id or None, client_secret_env) or ""`（去掉 `int()` 判定与本地兜底，作用域逻辑下沉注入方）。
  同命令见绿。
- [x] 1.3 (test) integration：`tests/integration/test_managed_oauth_client_secret_scope.py` —
  用真实 `agent_store` + `agent_secrets`（`apply_migrations` + tmp DB）验证 `server.py` 注入的映射 resolver：
  - 以 agent **名字** 命中该 agent 的 per-agent client_secret；
  - per-agent 缺失、全局(agent_id NULL)有值 → 命中全局兜底；
  - 未知名字且全局无值 → None。
  跑该文件见红。
- [x] 1.4 (impl) `server.py`：新增 `_resolve_agent_client_secret(agent_ref, env)`（`isdigit`→int；否则 `agent_store.get_by_name(name).id`；`get_decrypted(id,env)` → 全局兜底），`set_client_secret_resolver(_resolve_agent_client_secret)` 替换原 `get_decrypted` 直连。同命令见绿。

## P2 — agent 侧三元组 agent 身份归一化

- [x] 2.1 (test) unit：`tests/unit/test_mcp_effective_agent_id.py` —
  `integrations/mcp/client._effective_agent_id`：
  - 传空/None + 单活跃 agent（patch `agent_config.active_agent` 返回名为 `bi-intern` 的 AgentFile）→ 返回 `"bi-intern"`；
  - 传非空 `"x"` → 原样返回 `"x"`（不覆盖）；
  - 传空 + `active_agent()` 返回 None → 返回 None。
  跑该文件见红。
- [x] 2.2 (impl) `integrations/mcp/client.py`：新增 `_effective_agent_id(agent_id)`（空→`agent_config.active_agent().name`，无则 None），在公开 `call_tool` 取到 `server` 后、调 `_call_via_session` 前 `agent_id = _effective_agent_id(agent_id)`。同命令见绿。
- [x] 2.3 (test) unit：在 `test_mcp_effective_agent_id.py` 增 `call_tool` 归一化断言 —
  patch `agent_config.active_agent` 与 `_call_via_session`（AsyncMock），`call_tool(..., agent_id=None)` → 断言 `_call_via_session` 收到的 `agent_id == "bi-intern"`；`agent_id="explicit"` → 收到 `"explicit"`。见红。
- [x] 2.4 (impl) 若 2.3 未直接绿：微调 `call_tool` 归一化接线使断言通过。见绿。

## 收尾

- [x] 3.1 层边界：`uv run python scripts/check_test_layers.py` 与 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过（P2 未引入 agent→platform 反向依赖；P1 映射只在 server.py）。
- [x] 3.2 门禁：`make test-pr` 与 `make test-integration-ci` 全绿（判据=无新增失败）。
- [x] 3.3 mypy：`uv run mypy src`（对改动文件无新增报错，对照 baseline）。
