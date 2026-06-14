# add-agent-im-access Tasks

> TDD：实现 task 先测试见红 → 实现见绿（最窄命令 `uv run pytest <file>::<test> -x -q`），测试在实现之前。迁移号 append after head、**勿硬编码**。脚手架阶段：**不接 materialize/runtime**（留阶段 3）。

## 1. 迁移：建群白名单表 + 能力列（Alembic）

- [x] 1.1 [测试] integration：head 后存在 `agent_im_groups`（列 agent_id/platform/group_id/created_at/created_by、PK(agent_id,platform,group_id)、FK→agents.id ON DELETE CASCADE）；`agents` 有 `supports_dm`/`supports_groups`（默认 0）（先红）
- [x] 1.2 [测试] integration：删除持有 agent_im_groups 行的 agent → 该表对应行级联清空（先红）
- [x] 1.3 [实现] 新迁移（append after head、勿硬编码）：`CREATE TABLE agent_im_groups`（FK CASCADE）+ `ALTER TABLE agents ADD COLUMN supports_dm/supports_groups INTEGER NOT NULL DEFAULT 0`；downgrade 反向 drop 表 + drop 列 → 1.1/1.2 转绿

## 2. store + admin API

- [x] 2.1 [测试] integration：`agent_im_group_store` bind/unbind/list 正确（named params、db 边界）；`agent_store` 读写 agents.supports_* 的 getter/setter 正确（先红）
- [x] 2.2 [实现] 新增 `agent_im_group_store`；`agent_store` 加 supports_* getter/setter → 2.1 转绿
- [x] 2.3 [测试] integration：admin API——`POST/DELETE /admin/agents/{name}/bindings/groups` 增删 agent_im_groups；能力开关端点设 agents.supports_*；viewer 写返回 403；目标 agent 不存在 404（先红）
- [x] 2.4 [实现] `agent_admin_api` 加群白名单绑定/解绑端点 + 能力开关端点（user 绑定端点不动）→ 2.3 转绿

## 3. 文档 + spec 同步

- [x] 3.1 `docs/architecture/data-model.md` §3.2 + ER 图：加 `agent_im_groups`（节点 + `agents ||--o{ agent_im_groups`，实线 FK）；agents 注记 `supports_dm`/`supports_groups` 列；`user_agents` 保持（用户准入源，phase 3 materialize）
- [x] 3.2 archive 时同步 delta 到 canonical：新增 `agent-im-access`、MODIFIED `agent-admin-api`/`agent-definition`

## 4. 收尾

- [x] 4.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [x] 4.2 确认本阶段**未接 materialize/runtime**（agent.yaml 无 im 块变更、准入闸未改）——那是阶段 3
- [x] 4.3 `openspec validate add-agent-im-access` 通过；checkbox 全 `[x]`
