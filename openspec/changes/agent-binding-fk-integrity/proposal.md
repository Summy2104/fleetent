# agent-binding-fk-integrity

> **Provisional**：agent 身份模型迁移**阶段 4**（依据 `docs/architecture/agent-identity-model.md`）。排在阶段 2/3 之后（同走 Alembic 单链，串行）；版本号不在此 pin。

## Why

身份模型 R1 要求平台侧所有 agent 引用为 `agent_id` INTEGER **FK→agents.id ON DELETE CASCADE**。阶段 2/3 已把偏离类型/键的表（agent_kbs/agent_skills/admin_state/session_meta）归一并补 FK；但另有一批表**早已是 INTEGER agent_id、却从未声明 FK**：`user_agents`、`channel_agents`、`agent_versions`、`agent_mcp_servers`、`agent_secrets`。后果：agent 删除时这些行变孤儿（靠手工清理兜底，非 DB 级保护）。本阶段把缺失的 FK 补齐，使"agent 删除即级联清理全部绑定"由约束保证。

## What Changes

- **补 FK→agents.id ON DELETE CASCADE**（Alembic 新迁移，append after head、不硬编码）于：`user_agents`、`channel_agents`、`agent_versions`、`agent_mcp_servers`、`agent_secrets`（均已 INTEGER agent_id，仅加约束、无值变更；SQLite 经 batch 重建加 FK，保留各自主键/唯一约束）。
- **不含**：`agent_mcp_server_bindings`、`agent_oauth_bindings`（已有 FK）；`connectors.agent_id`（休眠列、never written——身份模型决定不强加 FK，待真实接入再规整）。
- **文档**：`data-model.md` §3.2 标注这批表已带 FK→agents.id ON DELETE CASCADE。

不碰列类型/键（阶段 2/3 已处理）、不碰 agent 侧/翻译边界（阶段 5）。

## Capabilities

### Modified Capabilities

- `agent-definition`: 平台侧 agent 绑定/从属表（user_agents / channel_agents / agent_versions / agent_mcp_servers / agent_secrets）SHALL 声明 FK→agents.id ON DELETE CASCADE——agent 删除级联清理其全部绑定，无孤儿；`connectors.agent_id` 休眠列除外

## Impact

- **owning package**：`platform`（Alembic 迁移）
- **public API surface**：无（仅加 DB 约束）
- **owned tables**：上述 5 表新增 FK→agents.id ON DELETE CASCADE（无列/值变更）
- **config namespace**：无
- **cross-module dependencies**：不碰 agent 零 platform import
- **migration / shim plan**：Alembic batch 重建加 FK（保留主键/唯一约束/索引）；forward-only；**FK 已全局启用**（见 data-model §2），故补 FK 后约束即时生效；迁移前若存量有违规孤儿行，先清理或在迁移内处理（pre-launch 窗口，多为空）
- **相邻切片**：依赖阶段 2/3 先落地（Alembic 单链串行）；apply 前 pull 确认 head
