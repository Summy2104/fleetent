# agent-binding-fk-integrity

> **Provisional**：agent 身份模型迁移**阶段 4**（依据 `docs/architecture/agent-identity-model.md`）。排在阶段 2/3 之后（同走 Alembic 单链，串行）；版本号不在此 pin。

## Why

身份模型 R1 要求平台侧所有 agent 引用为 `agent_id` INTEGER **FK→agents.id ON DELETE CASCADE**。阶段 2/3 已把偏离类型/键的表（agent_kbs/agent_skills/admin_state/session_meta）归一并补 FK；但另有一批表**早已是 INTEGER agent_id、却从未声明 FK**：`user_agents`、`channel_agents`、`agent_versions`、`agent_mcp_servers`、`agent_secrets`。后果：agent 删除时这些行变孤儿（靠手工清理兜底，非 DB 级保护）。本阶段把缺失的 FK 补齐，使"agent 删除即级联清理全部绑定"由约束保证。

**一并做 MCP 两表正名（方案 A）**：两张 MCP 表命名与 skills/kbs 不一致、且角色反着——`agent_mcp_servers` 其实是**定义/注册表**（存 transport/url/auth，含全局 `agent_id=NULL` 行），却长得像绑定表；真正的绑定是 `agent_mcp_server_bindings`（带 `_bindings` 后缀，反成异类）。借本阶段已在 batch 重建这些表之机一并正名，对齐 `agent_skills`/`agent_kbs`（绑定 = `agent_<物>`）与 `connectors`（注册表无 `agent_` 前缀）两条既有惯例。纯命名整洁，运行时行为不变。

## What Changes

- **补 FK→agents.id ON DELETE CASCADE**（Alembic 新迁移，append after head、不硬编码）于：`user_agents`、`channel_agents`、`agent_versions`、`mcp_servers`（即正名后的原 `agent_mcp_servers` 注册表）、`agent_secrets`（均已 INTEGER agent_id，仅加约束、无值变更；SQLite 经 batch 重建加 FK，保留各自主键/唯一约束）。
- **MCP 两表方案 A 改名**（同一 Alembic 迁移内，**先腾名再换、无需临时名**）：
  - ① `agent_mcp_servers`（定义/注册表）→ **`mcp_servers`**（腾出 `agent_mcp_servers` 名；本表本批补 FK）；索引 `idx_agent_mcp_servers_agent`→`idx_mcp_servers_agent`。
  - ② `agent_mcp_server_bindings`（绑定）→ **`agent_mcp_servers`**（沿用既有 FK，PK/`created_by` 不变）。
  - 终态：`mcp_servers`（注册）+ `agent_mcp_servers`（绑定），与 `agent_skills`/`agent_kbs` 并行。
  - 代码随动：`agent_mcp_server_store.py`（注册表 SQL 表名→`mcp_servers`）、`agent_store.py` bind/unbind/list（绑定 SQL 表名→`agent_mcp_servers`）；store 文件/函数名建议同步正名（避免「表名已正、代码名仍反」），不强制但推荐。
- **不强加 FK**：`agent_oauth_bindings`（已有 FK，不动）；`connectors.agent_id`（休眠列、never written——不强加 FK，待真实接入再规整）。
- **文档**：`data-model.md` §3.2 + ER 图标注这批表 FK，并把 MCP 两表更新为 `mcp_servers`/`agent_mcp_servers` 新名与角色。

不碰列类型/键（阶段 2/3 已处理）、不碰 agent 侧/翻译边界（阶段 5）。

## Capabilities

### Modified Capabilities

- `agent-definition`: 平台侧 agent 绑定/从属表（user_agents / channel_agents / agent_versions / `mcp_servers` / agent_secrets）SHALL 声明 FK→agents.id ON DELETE CASCADE——agent 删除级联清理其全部绑定，无孤儿；`connectors.agent_id` 休眠列除外。并规整 MCP 两表命名：注册表 = `mcp_servers`（无 `agent_` 前缀，对齐 `connectors`）、绑定表 = `agent_mcp_servers`（对齐 `agent_skills`/`agent_kbs`）

## Impact

- **owning package**：`platform`（Alembic 迁移 + `connector_management/agent_mcp_server_store.py` + `agent_store.py` MCP 绑定 SQL）
- **public API surface**：无新增/变更签名（仅加 DB 约束 + 表名内部更新）；若同步正名 store 函数/文件，属内部重命名，调用方随动
- **owned tables**：5 表新增 FK→agents.id ON DELETE CASCADE（无列/值变更）；MCP 两表改名 `agent_mcp_servers`→`mcp_servers`（注册）、`agent_mcp_server_bindings`→`agent_mcp_servers`（绑定，FK 不变）；索引 `idx_agent_mcp_servers_agent`→`idx_mcp_servers_agent`
- **config namespace**：无（YAML 侧 `mcp_servers[]` 配置键与 DB 表同名属巧合、不涉及）
- **cross-module dependencies**：不碰 agent 零 platform import
- **migration / shim plan**：Alembic batch 重建加 FK（保留主键/唯一约束/索引）；MCP 改名在同一迁移内**先 `agent_mcp_servers`→`mcp_servers` 腾名、再 `agent_mcp_server_bindings`→`agent_mcp_servers`**（顺序换、无需临时名）；forward-only、downgrade 反向；**FK 已全局启用**（见 data-model §2），补 FK 后即时生效；迁移前若存量有违规孤儿行，先清理或迁移内处理（pre-launch 窗口，多为空）
- **相邻切片**：依赖阶段 2/3 先落地（Alembic 单链串行）；已核当前未归档 change 无一碰 MCP 表/store（`unified-file-exchange` 的 `mcp_servers[]` 是 YAML 配置键、非 DB 表）；apply 前 pull 确认 head 与无新增碰撞
