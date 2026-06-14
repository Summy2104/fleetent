# rename-connector-to-im

> IM 访问模型（[im-access-model](../../../docs/architecture/im-access-model.md) §8 阶段 4）**最后一棒：纯改名，零行为**。把 IM 语境下被重载的 "connector" 命名正名为 `im`，消除与 tool OAuth `connectors` / `kb_connectors` / owner 级 `im_connectors` 表 的混淆。**无管理库迁移**（agent.yaml 是 agent 侧配置、ConnectorAccess 是 Python、allow_channels 是 agent.yaml 字段）；不碰 Alembic 链。apply 须等阶段 3b 落地（两者都改 data-model.md，且本阶段改的是 post-3b 的代码）。

## Why

"connector" 在 fleetent 里至少四义：IM bot 连接（agent.yaml `connectors.slack/telegram` + `ConnectorAccess`）、工具 OAuth（`connectors` 表 + connector_admin_api）、KB 数据源（`kb_connectors`）、owner 级 IM 平台配置（`im_connectors` 表）。读代码须脑内消歧。阶段 1–3b 功能落地时刻意**零改名**（降风险）；本阶段把 **IM bot 连接那一义**正名为 `im`，与已有的 `im_gateway` / `im_users` 命名空间一致。纯改名、运行时行为不变。

## What Changes（纯改名，零行为）

**改名映射（仅 IM bot 连接这一义）**：

| 旧 | 新 |
|---|---|
| agent.yaml block `connectors:` | `im:` |
| `connectors.slack` / `connectors.telegram` | `im.slack` / `im.telegram` |
| Python `AgentConnectors`（顶层容器） | `ImBinding` |
| `SlackConnector` / `TelegramConnector` | `SlackBinding` / `TelegramBinding` |
| `ConnectorAccess` | `ImAccess` |
| `access.allow_channels` 字段 | `allow_groups`（语义已在阶段 3 变窄为群白名单，本阶段对齐名字） |

**代码改名点**（surgical——只动 IM-gateway 这一义）：`agent_config.py`（类 + block 名）、`im_gateway/slack.py`·`telegram.py`·`slack_supervisor.py`·`telegram_supervisor.py`·`connector_registry.py`·`normalizer.py`·`access.py`（`agent.connectors.*`→`agent.im.*`、`ConnectorAccess`→`ImAccess`、`allow_channels`→`allow_groups`）、`materialize.py`（写 `im` 块）、`server.py`（连接器 supervisor 引用）。

**铁律——绝不碰的"connector"另三义**：
- 工具 OAuth：`connector_admin_api` / `connector_config_store` / `connectors` 表 / `agent_oauth_bindings` —— 不动。
- KB 数据源：`kb_connector_store` / `kb_connectors` 表 / `knowledge_base/connectors/*` —— 不动。
- owner 级 IM 平台配置：`im_connectors` 表（已是 im_ 前缀，本就独立）—— 不动。

**spec 名字同步**：7 个相关 spec（`per-agent-slack-connector`、`per-agent-telegram-connector`、`per-agent-im-access`、`file-agent-runtime`、`im-connector-config`、`im-connector-registry`、`im-gateway`）的 `ConnectorAccess`/`connectors.`/`allow_channels` 措辞随代码改名一并更新——**apply 时与代码改名同一次 find-replace 完成**（避免脱离代码单独抄写、对不齐）。

**向后兼容**：现有 agent.yaml 用 `connectors:`/`allow_channels` 将失效——pre-launch 窗口，重写/重置即可，不引入别名 shim（YAGNI）。

## Capabilities

### Modified Capabilities
- `per-agent-slack-connector` / `per-agent-telegram-connector`：agent.yaml 声明从 `connectors.slack/telegram` 改为 `im.slack/telegram`，`ConnectorAccess`→`ImAccess`，`allow_channels`→`allow_groups`（纯命名，行为不变）。
- `per-agent-im-access`：准入闸引用的访问块从 `ConnectorAccess` 改为 `ImAccess`，`allow_channels`→`allow_groups`（命名对齐阶段 3 的群白名单语义）。
- （`im-gateway` / `im-connector-config` / `im-connector-registry` / `file-agent-runtime` 的相关命名提及随之同步。）

## Impact

- **owning package**：`runtime`/`im_gateway`（agent_config + 适配器 + 闸引用）、`platform`（materialize 写 `im` 块）。
- **public API surface**：agent.yaml schema 改名（`connectors`→`im`、`allow_channels`→`allow_groups`）——破坏现有 agent.yaml（pre-launch 重写）；Python 类改名（内部）。无 HTTP API 变更。
- **owned tables**：无（不碰任何表；`im_connectors`/`connectors`/`kb_connectors` 都不动）。
- **config namespace**：agent.yaml `connectors.*` → `im.*`。
- **migration / shim plan**：**无管理库迁移**；不碰 Alembic 链；纯代码 + agent.yaml 字段改名；无别名 shim。
- **cross-module dependencies**：surgical 改名只动 IM-gateway 一义；不碰 tool/KB connector 与 im_connectors 表。
- **风险**：① 重载词改名误伤——必须只动 IM bot 连接这一义（grep 区分 `agent.connectors`/ConnectorAccess vs connector_admin_api/kb_connector/im_connectors 表）；② agent.yaml 破坏（pre-launch 接受）。
- **相邻切片**：**apply 须排在阶段 3b 之后**（都改 data-model.md；本阶段改 post-3b 代码）；本阶段无 Alembic 迁移故不卡链；已核无在跑 change 碰这些文件；apply 前 pull 确认。
