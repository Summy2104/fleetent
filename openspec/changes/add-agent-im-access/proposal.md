# add-agent-im-access

> IM 访问模型（[im-access-model](../../../docs/architecture/im-access-model.md)）**阶段 2**：立"群白名单表 + agent IM 能力列 + admin 配置入口"的脚手架。**暂不接 materialize/runtime**（阶段 3 接线 + 闸分流）。head=087（新迁移 088，**勿硬编码**）；已核 `knowledge-base-standalone-service` 不碰这些表/文件。

## Why

阶段 1 已删死的渠道路由表。IM 访问模型需要平台侧三类可配置项喂给（阶段 3 的）materialize：① agent 的私聊/群聊**能力**声明；② **群白名单**（agent 准在哪些群）；③ **用户准入**（哪些 User 能用此 agent）。其中用户准入的 `user_agents` 表已存在（阶段 1 保留、未动），只缺 ① ②。本阶段把缺的表/列/admin 入口建好，让 admin 可以开始配置，runtime 接线留阶段 3。

设计已定（见设计文档 §3/§6/§10）：
- **用户准入用 `user_agents`、不改名**（跨平台、非 IM 专属，不加 im 前缀）。
- **能力 `supports_dm`/`supports_groups` 落 `agents`**（agent 级非版本化配置，并入 allowed_skills/features 族；非 agent_versions，避免版本回滚耦合）。
- **群白名单 `agent_im_groups` 新建**（IM 平台特定，带 im 前缀）。

## What Changes

- **Alembic 迁移**（append after head、勿硬编码）：
  - `CREATE TABLE agent_im_groups`：`agent_id INTEGER NOT NULL FK→agents.id ON DELETE CASCADE`、`platform TEXT NOT NULL`、`group_id TEXT NOT NULL`、`created_at TEXT NOT NULL`、`created_by TEXT`，PK `(agent_id, platform, group_id)`。默认无行 = 不进任何群（安全默认在阶段 3 的闸体现）。
  - `ALTER TABLE agents ADD COLUMN supports_dm INTEGER NOT NULL DEFAULT 0` + `supports_groups INTEGER NOT NULL DEFAULT 0`（默认全关；`ADD COLUMN` 无需重建）。
- **store**：新增 `agent_im_group_store`（bind/unbind/list group，named params、db 边界）；`agent_store` 加读写 `agents.supports_dm/groups` 的 getter/setter。
- **admin API**（`agent_admin_api`）：新增群白名单配置端点（`POST/DELETE /admin/agents/{name}/bindings/groups`，按 platform+group_id）+ 能力开关端点（设 supports_dm/groups）；user 准入端点（user_agents）阶段 1 已有、不动。
- **不在本阶段**：materialize 读这些 → agent.yaml `im` 块、准入闸按 chat_type 分流、`ConnectorAccess`→`ImAccess` 演进——全留**阶段 3**。本阶段产物 admin 可配、但 runtime 尚不消费（脚手架）。
- **文档**：`data-model.md` §3.2 + ER 图加 `agent_im_groups`（节点 + `agents ||--o{ agent_im_groups`）+ agents 的 supports_* 列注记。

## Capabilities

### Added Capabilities
- `agent-im-access`: agent IM 访问控制的平台侧存储与配置——`agents.supports_dm/supports_groups` 能力声明 + `agent_im_groups` 群白名单 + admin 配置端点。运行时强制（闸）由阶段 3 落地。

### Modified Capabilities
- `agent-admin-api`: 新增 IM 群白名单绑定/解绑端点 + agent IM 能力开关端点（与既有 user 绑定端点并列）。
- `agent-definition`: agent 绑定表 FK 级联 requirement 的覆盖列表加入 `agent_im_groups`（INTEGER agent_id FK→agents.id ON DELETE CASCADE）。

## Impact

- **owning package**：`platform`（Alembic + 新 `agent_im_group_store` + `agent_store` 能力 getter/setter + `agent_admin_api` 端点）。
- **public API surface**：新增 admin 端点（群白名单 + 能力开关）；无删除/破坏。
- **owned tables**：`CREATE agent_im_groups`；`agents` 加 `supports_dm`/`supports_groups` 两列（默认 0）。
- **config namespace**：无（agent.yaml `im` 块演进留阶段 3）。
- **cross-module dependencies**：不碰 agent 零 platform import；materialize/runtime 本阶段不接。
- **migration / shim plan**：append after head（088，勿硬编码）；`CREATE TABLE` + `ADD COLUMN`（无重建）；downgrade 反向 drop。
- **相邻切片**：阶段 3 在其后（materialize + 闸，依赖本阶段的表/列）；已核 `knowledge-base-standalone-service` 不碰；apply 前 pull 确认 head 与无新增碰撞。
