# agent-binding-fk-integrity Tasks

> Provisional（阶段 4，排在阶段 2/3 后）。TDD：先测试见红、再实现见绿。

## 1. 补 FK（Alembic）

- [ ] 1.1 [测试] integration：head 后 `user_agents` / `channel_agents` / `agent_versions` / `agent_mcp_servers` / `agent_secrets` 各有 FK→agents.id ON DELETE CASCADE；各自主键/唯一约束/索引保留（先红）
- [ ] 1.2 [测试] integration：删除一个持有这些绑定的 agent → 五表对应行级联清空（FK 已全局启用，cascade 生效）；非空孤儿存量行迁移前已清理/处理（先红）
- [ ] 1.3 [实现] Alembic 新迁移（append after head、勿硬编码）：batch 重建五表加 FK→agents.id ON DELETE CASCADE（保留主键/唯一约束/索引）；迁移内先清理（或拒绝）违规孤儿行；downgrade 去 FK → 1.1/1.2 转绿

## 2. 守护 + 文档

- [ ] 2.1 [测试] integration/unit：守护——五表 FK 存在 + 级联；`connectors.agent_id` 仍无 FK（休眠列，确认未误加）
- [ ] 2.2 `docs/architecture/data-model.md` §3.2：标注这五表已带 FK→agents.id ON DELETE CASCADE；注明属 identity-model 阶段 4

## 3. 收尾

- [ ] 3.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：agent 删除路径级联正确、无回归）
- [ ] 3.2 `openspec validate agent-binding-fk-integrity` 通过；checkbox 全 `[x]`
