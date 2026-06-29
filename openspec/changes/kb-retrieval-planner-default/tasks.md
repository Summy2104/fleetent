## 1. retrieval_policy 新增 use_planner 字段

- [ ] 1.1 写 unit 测试:`AgentRetrievalPolicy` 默认 `use_planner=false`;agent.yaml 可解析该字段(见红)
- [ ] 1.2 在 `agent_config.AgentRetrievalPolicy` 加 `use_planner: bool = False`;跑 1.1 见绿

## 2. _search_knowledge 按 policy 走 planner

- [ ] 2.1 写 integration 测试:`use_planner=false`(默认)时检索走 `search(mode=...)`,行为与当前一致(见红/对照基线)
- [ ] 2.2 写 integration 测试:`use_planner=true` 且图谱有数据时,关系型 query 经 planner 命中 graph 证据,返回 KnowledgeChunk 喂入预算管线(见红)
- [ ] 2.3 写 integration 测试:`use_planner=true` 但无图数据时,planner 回落 hybrid、不报错(见红)
- [ ] 2.4 在 `long_term_ctx._search_knowledge` 按 `retrieval_policy.use_planner` 二选一:真 → `plan_knowledge_search` + `execute_knowledge_search_plan`;假 → 现有 `search`;下游预算/选择不变；跑 2.1–2.3 见绿（测试 monkeypatch 指真实 `fleetent.long_term_ctx` 子模块，勿 patch 旧 shim）

## 3. 收尾验证

- [ ] 3.1 跑 `make test-pr` + `make test-unit-ci`(含 76% 覆盖率关)+ `make test-integration-ci`,判"对照 main 基线无新增失败、覆盖率不破 76"
- [ ] 3.2 ruff format/check 改动文件;module-boundaries 检查通过(long_term_ctx 仍 ✗→ platform）;`openspec validate kb-retrieval-planner-default` 通过
- [ ] 3.3 更新 `docs/capabilities/knowledge-base.md` 或 agent 文档:retrieval_policy.use_planner opt-in、关系型 query 升级 graph、默认关行为不变(非代码产物,人工确认后再 commit)
