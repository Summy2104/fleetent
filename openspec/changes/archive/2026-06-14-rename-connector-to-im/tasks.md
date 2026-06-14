# rename-connector-to-im Tasks

> 纯改名、零行为。无管理库迁移。**铁律：只动"IM bot 连接"一义**，不碰 tool OAuth `connectors`/`connector_admin_api`、KB `kb_connectors`、owner 级 `im_connectors` 表。验证=行为不变（测试全绿）+ grep 确认只改了该改的。apply 须在阶段 3b 落地后。

## 1. agent_config 改名（核心）

- [x] 1.1 [测试] unit：`im` block 解析——`ImBinding`（顶层，含 supports_dm/groups + slack/telegram）、`SlackBinding`/`TelegramBinding`、`ImAccess`（allow_users/allow_groups/allow_all_users/require_approval）；agent.yaml `im.slack.access.allow_groups` 解析正确（先红）
- [x] 1.2 [实现] `agent_config.py`：`AgentConnectors`→`ImBinding`、`SlackConnector`→`SlackBinding`、`TelegramConnector`→`TelegramBinding`、`ConnectorAccess`→`ImAccess`、字段 `allow_channels`→`allow_groups`、block 名 `connectors`→`im`；supports_dm/groups 移到 `ImBinding` → 1.1 转绿

## 2. IM-gateway 消费方改名

- [x] 2.1 [实现] `im_gateway/`：`slack.py`/`telegram.py`/`slack_supervisor.py`/`telegram_supervisor.py`/`connector_registry.py`/`normalizer.py`/`access.py` 把 `agent.connectors.*`→`agent.im.*`、`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups`
- [x] 2.2 [实现] `materialize.py`：写 agent.yaml 的块名 `connectors`→`im`、access 字段名同步；`server.py`：连接器 supervisor 引用随动
- [x] 2.3 [测试] integration：闸/解析/materialize 行为**不变**（DM/群准入、默认关、materialize 填值都与改名前一致）（先红或现态确认）

## 3. spec 名字同步（与代码同一次 find-replace）

- [x] 3.1 [实现] 同步 7 个 spec 的 IM 义命名：`per-agent-slack-connector`/`per-agent-telegram-connector`/`per-agent-im-access`/`file-agent-runtime`/`im-connector-config`/`im-connector-registry`/`im-gateway` —— `ConnectorAccess`→`ImAccess`、`connectors.slack/telegram`→`im.slack/telegram`、`allow_channels`→`allow_groups`；写对应 delta 供 archive 同步 canonical

## 4. 文档 + 收尾

- [x] 4.1 `docs/architecture/data-model.md` §3.3：agent.yaml 块 `connectors`→`im`、字段名同步；`im-access-model.md` 标阶段 4 完成（命名映射已落地）
- [x] 4.2 **铁律核验**——全仓 grep：IM 义 `agent.connectors`/`ConnectorAccess`/`SlackConnector`/`allow_channels` 已清零；而 tool `connector_admin_api`/`connectors` 表、KB `kb_connectors`、`im_connectors` 表 **完好未被误改**
- [x] 4.3 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（纯改名→行为不变）
- [x] 4.4 `openspec validate rename-connector-to-im` 通过；checkbox 全 `[x]`
