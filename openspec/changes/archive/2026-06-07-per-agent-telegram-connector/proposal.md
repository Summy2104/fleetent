## Why

`im_gateway/telegram.py` 是 agent-runtime 里最后一处 `import fleetent.platform`——它通过 `im.resolve` 读 owner-level 连接器配置、`im.report_status`/`im.heartbeat` 反向写 platform 的 `im_connectors` 表,违反 CLAUDE.md「Agent / Platform 解耦」。更深层问题:telegram 仍是 owner-level、由 platform `ConnectorManager` 拉起,无法在独立 `fleetent agent run` 进程里运行;而 Slack 早已迁移为 per-agent(`agent.yaml` 声明 + `SlackSupervisor` + agent 进程拉起)。本变更把 telegram 对齐 Slack,完成 agent-runtime 对 platform 的彻底解耦。

## What Changes

- **配置**:`agent.yaml` 新增 `connectors.telegram`(`TelegramConnector{bot_token_env, channels}`,env 引用,禁止内联 secret),镜像 `connectors.slack`;`AgentConfigIndex` 新增 `telegram_agents()`。
- **适配器**:`telegram.py` 去掉 `import fleetent.platform`;`run(agent_name, owner_id, config)` 对齐 `slack.run`,删除 `im.resolve`/`im.report_status`/`im.heartbeat` 与 `_heartbeat_loop`;`create_app` 在 `NormalizedMessage` 上 stamp `agent_name` 并支持 `channels` 过滤。
- **Supervisor**:新增 `im_gateway/telegram_supervisor.py`(`TelegramSupervisor`,镜像 `SlackSupervisor`,零 platform 依赖,内存持有 per-agent 状态)。
- **agent 进程拉起**:`runtime/agent_app.py` 在 agent 运行时同时启动 `TelegramSupervisor`(与 Slack 并列)。
- **退役 owner-level telegram**:server `_connector_manager` 移除 telegram factory;`_telegram_adapter_configured()` 改读 `agent.yaml`;owner-level `connector_config` 的 telegram 凭证 schema 移除(仅留 whatsapp);owner-level 连接器生命周期不再启动 telegram。
- **行为对齐**:telegram 不再写 `im_connectors` 表的 status/heartbeat;状态由 supervisor 内存持有,与 Slack 一致。**BREAKING**(owner-level telegram 配置/状态面):telegram 凭证从 owner-level `.env`/DB 迁移到 `agent.yaml`。

## Capabilities

### New Capabilities
- `per-agent-telegram-connector`: per-agent Telegram 连接(agent.yaml 声明、按 agent 监督、连接隐式定位 agent、channel 过滤),镜像 `per-agent-slack-connector`。

### Modified Capabilities
- `im-connector-config`: owner-level 凭证 schema 移除 telegram(仅留 whatsapp);telegram 改为 per-agent env 引用。
- `im-connector-registry`: telegram 排除在 owner-level 连接器生命周期之外(镜像 slack 的排除)。

## Impact

- 代码:`agent_config.py`、`im_gateway/telegram.py`、新增 `im_gateway/telegram_supervisor.py`、`runtime/agent_app.py`、`server.py`、`platform/im_gateway_management/connector_config.py`。
- 测试:新增 telegram supervisor + per-agent create_app 测试;改/删 owner-level telegram 状态测试(`test_im_adapter_status`、`test_im_adapter_owner`);更新 `test_per_agent_slack_wiring`、`test_agent_config`、server lifespan、owner-level connector_config/registry 测试。
- 无 schema 迁移(`im_connectors` 表保留,telegram 行变 inert,与 slack 同处理);无新依赖。
