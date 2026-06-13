# unify-agent-state-id Tasks

> Provisional（阶段 3，排在阶段 2 后）。每个实现 task 严格 TDD：先测试见红、再实现见绿；迁移类含升级路径测试 + schema 守护断言。

## 1. agent_admin_state 主键 name→id（Alembic）

- [ ] 1.1 [测试] integration：head 后 `agent_admin_state` 以 `agent_id`(INTEGER) 为键、有 FK→agents.id ON DELETE CASCADE、无 agent name 键；升级路径——存量按 name 键的行经 agents 解析为 agent_id 重建（先红）
- [ ] 1.2 [实现] Alembic 新迁移（append after head、勿硬编码）：batch 重建 `agent_admin_state` 主键为 `agent_id` + FK + name→id 数据迁移；downgrade 回 name 键 → 1.1 转绿

## 2. session_meta.agent_name → agent_id（Alembic）

- [ ] 2.1 [测试] integration：head 后 `session_meta` 以 `agent_id`(INTEGER)+FK 引用 agent、无 agent_name 列、`user_id` 不变；升级路径 name→id 解析（先红）
- [ ] 2.2 [实现] Alembic 迁移（可与 1.2 同一迁移）：`session_meta` agent_name→agent_id + FK + 数据迁移；`user_id` 不动 → 2.1 转绿

## 3. 代码：键/列 int 化 + 调用方 name→id 解析

- [ ] 3.1 [测试] integration：`agent_admin_store` / `session_admin_store` 以 int agent_id CRUD 正常；`server.py` 的 agent status 查询、console / chat / askit apply 路径按 `{name}` 入参时正确解析 name→id（先红或现态确认）
- [ ] 3.2 [实现] 两 store 键/列改 int；调用方（server.py status、agent_management_console、chat_management、askit_console apply）调 store 前解析 name→id（HTTP 路由对外形态不变）→ 3.1 转绿

## 4. 守护 + 文档

- [ ] 4.1 [测试] unit：守护——`agent_admin_state` / `session_meta` 不再以 agent name 键/列引用 agent；agent 删除级联清理两表行
- [ ] 4.2 `docs/architecture/data-model.md` §3.2：admin_state 键、session_meta.agent_name 描述改为 agent_id + FK；注明属 identity-model 阶段 3

## 5. 收尾

- [ ] 5.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败
- [ ] 5.2 全仓 grep：对 admin_state / session_meta 按 name 寻址 agent 的残留清零（迁移历史/归档除外）
- [ ] 5.3 `openspec validate unify-agent-state-id` 通过；checkbox 全 `[x]`
