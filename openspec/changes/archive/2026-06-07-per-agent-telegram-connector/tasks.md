## 1. agent.yaml Telegram 连接器声明

- [x] 1.1 写失败测试 `tests/unit/test_agent_config.py`:`connectors.telegram` 解析(`bot_token_env`/`channels`)、`telegram_agents()` 返回声明 telegram 的 agent、内联 secret 被拒。运行 `uv run pytest tests/unit/test_agent_config.py -x -q` **必须红**
- [x] 1.2 实现:`agent_config.py` 加 `TelegramConnector{bot_token_env, channels}`、`AgentConnectors.telegram`、`AgentConfigIndex.telegram_agents()`。运行 1.1 **绿**

## 2. Telegram 适配器对齐 slack（去 platform、新签名、stamp agent、channel 过滤）

- [x] 2.1 写失败测试 `tests/unit/test_telegram_per_agent.py`(镜像 `test_slack_per_agent.py`):`create_app(agent_name, owner_id, config)` 在 `NormalizedMessage` stamp `agent_name`;`channels` 非空过滤、空全放行。新增断言「`fleetent.im_gateway.telegram` 不 import `fleetent.platform`」。运行 **必须红**
- [x] 2.2 实现:重写 `im_gateway/telegram.py`——删 `from fleetent.platform import ...`、`_heartbeat_loop`、`im.*`;`run(agent_name, owner_id, config)` 对齐 `slack.run`;`create_app` 接 `agent_name`、stamp 到 `NormalizedMessage.agent_name`、按 `config.channels` 过滤。运行 2.1 **绿**
- [x] 2.3 删除/改写过时 owner-level 状态测试:`tests/unit/test_im_adapter_status.py`(telegram 自报状态语义已废)、`tests/unit/test_im_adapter_owner.py` 的 telegram 用例(slack 用例保留)。运行二者 **绿**

## 3. TelegramSupervisor（im_gateway，零 platform，内存状态）

- [x] 3.1 写失败测试 `tests/unit/test_telegram_supervisor.py`(镜像 `test_slack_supervisor.py`):每个声明 telegram 的 agent 一连接、缺 token→`unconfigured` 且隔离、reload 增删、stop→`stopped`。运行 **必须红**
- [x] 3.2 实现 `im_gateway/telegram_supervisor.py`:`TelegramSupervisor`,`_resolve_config` 取 `bot_token_env`(+channels),start/stop/reload/start_from_index/stop_all/running/status。运行 3.1 **绿**

## 4. agent 进程拉起（agent_app）

- [x] 4.1 写失败测试(`tests/integration/` 镜像 slack wiring):`agent_app.start_agent` 启动 TelegramSupervisor、`AgentRuntime.stop` 停止之。运行 **必须红**
- [x] 4.2 实现 `runtime/agent_app.py`:`AgentRuntime` 持有 telegram supervisor;`start_agent` 启动、`stop` 停止(与 slack 并列)。运行 4.1 **绿**

## 5. 退役 owner-level telegram（server + connector_config + registry）

- [x] 5.1 更新 `tests/integration/test_per_agent_slack_wiring.py`:flip 为 `"telegram" not in _connector_manager._factories` 且 `"telegram" not in PLATFORM_CONFIG_KEYS`;server lifespan `_telegram_adapter_configured()` 改读 agent.yaml 的测试。运行 **必须红**
- [x] 5.2 实现:`server.py` 从 `_connector_manager` 移除 telegram factory、`_telegram_adapter_configured()` 镜像 `_slack_adapter_configured()`;`connector_config.py` 从 `PLATFORM_CONFIG_KEYS`/`_ENV_MAP` 移除 telegram。运行 5.1 **绿**
- [x] 5.3 修复其余因 owner-level telegram 退役而破的测试(connector_manager/config/store owner-scoped、admin、server lifespan、config、skill_registry platforms 等),逐一改到新契约。运行相关分层 **绿**

## 6. 收尾

- [x] 6.1 `uv run ruff format src tests && uv run ruff check src tests` + `uv run mypy src`(改动文件零问题)
- [x] 6.2 `env -u FLEETENT_HOME uv run pytest -x -q` 全绿 + `uv run python scripts/check_test_layers.py`(本变更文件不引入新违规)
- [x] 6.3 复核:`grep -rn "import fleetent.platform" src/fleetent/im_gateway` 为空,整个 agent-runtime 零 platform import
