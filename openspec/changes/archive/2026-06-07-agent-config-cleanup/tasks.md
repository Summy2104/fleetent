## 1. 删除死字段（Schema 清理）

- [x] 1.1 Write failing test: `AgentFile` 加载含 `microsandbox_url` 字段的 yaml 应抛出 `ValidationError`
- [x] 1.2 Run test → 确认红（当前字段存在，不会报错）
- [x] 1.3 从 `src/fleetent/agent_config.py` 删除 `microsandbox_url`、`image_gen_url`、`image_gen_model`、`vision_url`、`vision_model` 五个字段定义
- [x] 1.4 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q` 全量 unit 绿
- [x] 1.5 Commit: `refactor(agent-config): remove dead schema fields (microsandbox_url, image_gen_*, vision_*)`

## 2. 接入 log_format（agent runtime 日志配置）

- [x] 2.1 Write failing test: `agent_app.boot()` 加载 `log_format: json` 的 agent 时应调用 `configure_structured_logging` 且使用 JSON renderer（mock `configure_structured_logging`）
- [x] 2.2 Run test → 确认红（boot 中目前不调用日志配置）
- [x] 2.3 在 `src/fleetent/runtime/agent_app.py` 的 `boot()` 函数中，在 `agent = agent_config.scan_home(home_dir)` 之后加入日志配置：读取 `agent.log_format` 和 `agent.observability.logging.*`，调用 `configure_structured_logging`
- [x] 2.4 Run test → 确认绿；运行 `uv run pytest tests/unit -x -q`
- [x] 2.5 Write test: `log_format: console` 时用 console renderer（覆盖默认值路径）
- [x] 2.6 Run test → 确认绿
- [x] 2.7 Commit: `feat(agent-app): configure logging from agent.yaml log_format at boot`

## 3. 更新 agent.yaml.example

- [x] 3.1 修复 `agents/default/agent.yaml.example` 第 1 行 typo（补回 `#`）
- [x] 3.2 删除 example 中 `microsandbox_url`、`image_gen_url`、`image_gen_model`、`vision_url`、`vision_model` 行及其注释
- [x] 3.3 在 `mcp_servers` 的 http 示例条目（`docs` server）中补充 `connect_timeout: 10.0` 和 `call_timeout: 30.0` 字段（带注释）
- [x] 3.4 在 `connectors:` 块中补充 `telegram:` 示例（`bot_token_env`、`channels`），紧接 slack 示例之后
- [x] 3.5 Commit: `docs(example): fix typo, remove dead fields, add telegram + mcp timeout examples`

## 4. 更新 .env.example

- [x] 4.1 在 `agents/default/.env.example` 中补充 `BILLING_DB_DSN=` 行（在 MCP servers 区块）
- [x] 4.2 补充 Telegram bot token 示例行（在 IM connectors 区块）
- [x] 4.3 Commit: `docs(example): add BILLING_DB_DSN and telegram token to .env.example`

## 5. 验证与收尾

- [x] 5.1 运行 `uv run pytest -x -q` 全量测试通过
- [x] 5.2 运行 `uv run python scripts/check_test_layers.py` 确认测试分层合规
- [x] 5.3 运行 `uv run ruff format src tests && uv run ruff check src tests` lint 通过
- [x] 5.4 运行 `uv run mypy src` 类型检查通过
