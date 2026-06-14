# descope-channel-agents

> IM 访问模型（[im-access-model](../../../docs/architecture/im-access-model.md)）**阶段 1**：删除已死的 `channel_agents` 渠道路由表及其直接依赖。**窄边界**——只动"表 + DB 侧消费者 + 表直接绑定的 spec"；agent.yaml `bindings.channels/users` 与 default-agent 查找顺序等**文件绑定路由模型**的清理**显式推迟到阶段 3**（彼时用 connector=agent 新模型替换、一并重写，不在此重复）。已核 `knowledge-base-standalone-service` 不碰本表；head=086（新迁移 087，**勿硬编码**）。

## Why

fleetent 采用**一 agent 一 bot**模型：连接器连接即 agent 身份，消息发给哪个 bot 就是哪个 agent。旧的"按 (platform, channel_id) 路由到 agent"（`channel_agents` 表）是"共享 bot 按频道路由"旧设计的遗骸：
- runtime 早已不读（`normalizer.get_agent_for_context` 直接返回 default，明文 "Bindings-based routing has been removed"）。
- 整条 DB→agent file→runtime 链端到端未接（materialize 不读 `channel_agents`，runtime 不读 `bindings.channels`）。
- `bound_version_id` 是无 FK 的休眠列（唯一 reader `get_channel_bound_version_id` 无生产调用）。

表 + 其 store/CLI/admin 端点纯属死代码与误导性 spec，删除零运行时风险。

## What Changes

- **Alembic 迁移**（append after head、勿硬编码）：`DROP TABLE channel_agents`（含休眠列 `bound_version_id`）。downgrade 重建空表 schema（不恢复数据；pre-launch）。
- **store**（`agent_store.py`）：删 `assign_channel` / `unassign_channel` / `get_agent_for_channel` / `list_channels_for_agent` / `get_channel_bound_version_id`。
- **CLI**（`admin_cli/agents.py`）：删 `assign-channel` / `unassign-channel` 命令。
- **admin API**（`agent_admin_api.py`）：删 `POST/DELETE /admin/agents/{name}/bindings/channels*` 端点 + bindings 列表里的 channels 部分（:123-128, :226-239, :252）。
- **archive 保护**（`agent_admin_store.references()` :124）：去掉 channel_agents 检查；保留 user_agents 检查（user_agents 阶段 2 才处理）。
- **文档**：`data-model.md` §3.2 去 `channel_agents`；ER 图删节点 + 边（`agents→channel_agents`、`agent_versions→channel_agents`）。

**显式不在本阶段（留阶段 3）**：agent.yaml `bindings.channels` / `bindings.users`、`default-agent` 的 "channel binding > user binding > default" 查找顺序、`Agent lookup priority order` requirement——这些属"文件绑定路由模型"，阶段 3 用 connector=agent + chat_type 闸模型替换时一并重写。本阶段后它们暂时仍提及 channel binding（已死、无 DB 背书），阶段 3 收口。

## Capabilities

### Removed Capabilities
- `channel-agent-binding`: 整个 capability 移除（`channel_agents` 存储 / "channel 优先于 user 的查找" / `bound_version_id` 审计列三条 requirement）——其建模的渠道路由 runtime 从不消费。

### Modified Capabilities
- `agent-admin-api`: 「Binding endpoints」去掉 channel 绑定/解绑端点，仅留 user 绑定。
- `agent-admin-ui`: 「Agent lifecycle and clone」去掉 Deploy-to-channel 动作（其调用的 channel 绑定端点已删）。
- `agent-definition`: agent 绑定表 FK 级联 requirement 的覆盖列表去掉 `channel_agents`（表已删）。
- `agent-template-clone`: clone 场景去掉 `channel_agents` 引用（仅留"不复制 user 绑定/default"）。
- `agent-lifecycle-toggle`: toggle-preserves 与 archive-protection 去掉 `channel_agents`（archive 保护仅按 user 绑定 + default）。

## Impact

- **owning package**：`platform`（Alembic + `agent_store.py` channel 段 + `admin_cli/agents.py` + `agent_admin_api.py` + `agent_admin_store.references`）。
- **public API surface**：移除 `/admin/agents/{name}/bindings/channels*` 端点（admin 面；deploy-to-channel UI 随之失效——已确认整撤）。其余 store/API 签名不变。
- **owned tables**：`DROP channel_agents`（无新增/列变更）。
- **config namespace**：无（agent.yaml `bindings.channels` 留阶段 3）。
- **cross-module dependencies**：不碰 agent 零 platform import。
- **migration / shim plan**：append after head（087，勿硬编码）；forward-only + downgrade 重建空表 schema（不恢复数据）。`channel_agents` 是 agent 删除级联子表之一——删表后 `delete_agent` 单条 `DELETE FROM agents` 的级联少一个子，无影响。
- **相邻切片**：阶段 2/3 在其后（IM 访问模型串行）；已核 `knowledge-base-standalone-service` 不碰本表/这些文件；apply 前 pull 确认 head 与无新增碰撞。
