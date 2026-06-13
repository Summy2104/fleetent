# unify-agent-binding-id Tasks

> 每个实现 task 严格 TDD：先写测试见红，再实现见绿。测试任务在对应实现任务之前。

## 1. schema + 数据迁移（Alembic）

- [ ] 1.1 [测试] integration：head 后 `agent_kbs.agent_id` 与 `agent_skills.agent_id` 为 INTEGER、各有 FK→agents.id ON DELETE CASCADE；复合主键/唯一约束保留（agent_kbs `(tenant_id,kb_id,agent_id)`、agent_skills `(agent_id,skill_name)`）（先红）
- [ ] 1.2 [测试] integration：升级路径——旧库三类存量行：① `agent_id` 数字串 → CAST 成对应 int；② `agent_skills` 中 `agent_id` 为 name 串且 agents 中存在 → 解析为该 agent 的 id；③ name 串解析不到 → 丢弃（先红）
- [ ] 1.3 [实现] 新增 Alembic 迁移（append after 081、勿硬编码）：batch 重建两表 agent_id 列为 INTEGER + 数据迁移（数字串 CAST / name 串 JOIN agents 解析 / 不可解析丢弃）+ 加 FK；downgrade 回 TEXT → 1.1/1.2 转绿

## 2. store 参数 int 化

- [ ] 2.1 [测试] integration：`skill_admin_store`（set_binding/enabled_skill_names/list_skills_for_agent/has_any_binding）与 `agent_kbs_store`（bind/unbind/list）以 int agent_id 正常 CRUD（先红或现态确认）
- [ ] 2.2 [实现] 两 store 的 `agent_id` 形参类型 str→int（SQL 文本不变）→ 2.1 转绿

## 3. 修 agent_skills name/id 混写 bug

- [ ] 3.1 [测试] integration（**bug 回归**）：经 agent 侧路由 `PUT /admin/agents/{name}/skills/{skill} {enabled:true}` 设绑定后，materialize 该 agent 能在 `allowed_skills` 看到该 skill（修复前看不到）；skill 侧路由设的绑定同样可见；两侧落同一 `(agents.id, skill)` 键（先红）
- [ ] 3.2 [实现] `agent_management_console.agent_admin_api`：`set_agent_skill`(:283) 与 skill 列表(:265-268) 调 store 前 `agent_store` 解析 name→id；`skill_admin_api`(:470) 去 `str()` 传 int → 3.1 转绿

## 4. agent_kbs 调用方去 str 包装

- [ ] 4.1 [测试] integration：kb 绑定经 agent 侧 / kb 侧路由设置后，materialize `list_kbs_for_agent(agent.id)` 读到（先红或现态确认）
- [ ] 4.2 [实现] `agent_admin_api`（kb bind :350）、`kb_admin_api`（:593）、materialize 读取一律传/用整数 `agent.id`，去掉 `str(agent.id)` 包装 → 4.1 转绿

## 5. 守护 + 文档

- [ ] 5.1 [测试] unit：守护——全仓无对 `agent_kbs`/`agent_skills` 的 `str(agent.id)` 写、无按 name 查这俩表的残留路径
- [ ] 5.2 `docs/architecture/data-model.md` §3.2：`agent_kbs`/`agent_skills` 描述从"TEXT str(id)"改为"INTEGER + FK→agents.id"；§3.3 若有 agent_skills bug 注记则更新为已修；注明属 agent-identity-model 阶段 2
- [ ] 5.3 复核 `docs/architecture/agent-identity-model.md`：阶段 2 标记进展（可选，落地后回填）

## 6. 收尾

- [ ] 6.1 `make test-pr` 全绿；`uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线无新增失败（重点：materialize 的 skill/kb 解析 + 控制台绑定 bug 已修）
- [ ] 6.2 全仓 grep 清零：对 agent_kbs/agent_skills 的 `str(agent.id)`、按 name 查这俩表（迁移历史与 openspec 归档除外）
- [ ] 6.3 `openspec validate unify-agent-binding-id` 通过；所有 checkbox 标记 `[x]`
