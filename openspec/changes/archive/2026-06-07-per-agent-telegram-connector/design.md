## Context

Slack 已是 per-agent 范式:`SlackConnector`(agent.yaml)+ `SlackSupervisor`(im_gateway,零 platform,内存状态)+ `slack.run(agent_name, owner_id, config)`(纯连接,不报状态)+ agent_app 拉起。Telegram 仍停留在旧 owner-level 范式:`im.resolve` 读配置、`im.report_status`/`im.heartbeat` 写 platform `im_connectors`、由 platform `ConnectorManager` 拉起(`agent_app` 根本不起 telegram)。telegram.py 因此带有 agent-runtime 唯一残留的 `import fleetent.platform`。

## Goals / Non-Goals

**Goals:**
- `telegram.py` 及整个 agent-runtime 零 `import fleetent.platform`。
- telegram 能在独立 `fleetent agent run` 进程里按 agent 运行,与 slack 完全同构。
- 配置来自 agent.yaml + env;状态由 supervisor 内存持有。

**Non-Goals:**
- 不动 IM 身份映射(`identity.py` 的 telegram 字段、`im_users`)——那是 platform 侧身份治理,与连接器配置正交。
- 不删 `im_connectors` 表或其 telegram 行(保留 inert,与 slack 迁移同处理);不做 schema 迁移。
- 不引入 platform→agent 推送;不改 whatsapp。

## Decisions

- **TelegramConnector** = `{bot_token_env: str, channels: list[str] = []}`(无 app_token——telegram 用 polling,非 Socket Mode)。`AgentConnectors.telegram` 新增;`telegram_agents()` 镜像 `slack_agents()`。
- **telegram.run 签名**改为 `run(agent_name, owner_id, config)` 对齐 slack。`config` 含 `bot_token`(+`channels`)。删除 `_heartbeat_loop` 与所有 `im.*`。`create_app(agent_name, owner_id, config)` 在 `NormalizedMessage` stamp `agent_name`(使 route 直接用连接定位 agent,跳过 channel→agent 查表),并按 `config.channels` 过滤(空=全放行),镜像 slack。
- **TelegramSupervisor**:新建 `im_gateway/telegram_supervisor.py`,结构镜像 `SlackSupervisor`(start/stop/reload/start_from_index/stop_all/running/status,内存 `_status`),`_resolve_config` 只取 `bot_token_env`(缺失→`unconfigured`)。采用并列独立 supervisor 而非抽公共基类——避免改动 slack 引入回归,保持与既有 per-connector-supervisor 先例一致。
- **agent_app**:`AgentRuntime` 同时持有 slack + telegram supervisor;`start_agent` 启动两者,`stop` 停两者。
- **server**:`_connector_manager` factories 去掉 telegram(变空,仅 owner-level whatsapp 概念保留);`_telegram_adapter_configured()` 改为 `any(a.connectors.telegram is not None ...)`,镜像 `_slack_adapter_configured()`。
- **owner-level 退役**:`connector_config.PLATFORM_CONFIG_KEYS`/`_ENV_MAP` 移除 telegram(仅留 whatsapp);owner-level 生命周期不再启动 telegram(`im-connector-registry` delta)。

## Risks / Trade-offs

- **测试面大**:owner-level telegram 状态/心跳测试(`test_im_adapter_status`、`test_im_adapter_owner` 的 telegram 用例)语义已不存在,需删除/改写为 supervisor 模型;`test_per_agent_slack_wiring` 中 `"telegram" in factories`/`PLATFORM_CONFIG_KEYS` 断言需 flip。逐一在 TDD 红阶段固定新契约。
- **Supervisor 重复**:TelegramSupervisor 与 SlackSupervisor 高度相似(可后续抽公共基类);此处选重复换取零 slack 回归风险与清晰 review。
- **BREAKING(运维面)**:已有用 `TELEGRAM_BOT_TOKEN` owner-level 配置的部署,需改到某 agent 的 `agent.yaml connectors.telegram` + 对应 env。proposal/spec 已标注。
