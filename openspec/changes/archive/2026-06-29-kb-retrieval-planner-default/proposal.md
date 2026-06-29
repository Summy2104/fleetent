## Why

`long_term_ctx` 的被动 KB 检索当前固定走 `search(mode=hybrid)`,从不经过 `plan_knowledge_search` / `execute_knowledge_search_plan`——后者能对关系型 query 升级到 graph、不足时 hybrid fill,是激活图谱能力(A+)在检索侧的入口。结果是 graph_search / planner 成为零生产调用的孤儿,图谱即便被 D3 填满也无人查询。本 change 让被动检索按 agent 配置 opt-in 走 planner,使图谱在 look-up 之外的关系型查询上发挥作用,同时默认行为不变。

## What Changes

- **retrieval policy 新增 planner opt-in**:`knowledge.retrieval_policy` 新增开关(如 `use_planner: bool`,默认 `false`)。开启时,agent 的被动 KB 检索路径 SHALL 经 `plan_knowledge_search` + `execute_knowledge_search_plan`(planner 规则:普通 query 走 hybrid、entity/relation-like query 先 graph、不足 hybrid fill),返回 `KnowledgeChunk` 喂入既有 long-term-ctx 预算/选择管线。
- **默认不变**:`use_planner=false`(默认)时,检索路径仍是 `search(mode=...)`,行为与当前一致。

不改变:`search()` / hybrid ranking / graph_search / planner 这些底层 API 的行为(本 change 只是把被动检索接到既有 planner,不改 planner 本身);long-term-ctx 的注入/预算/选择语义(planner 返回同样的 `KnowledgeChunk`);binding 作用域限制;token budget。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `agent-knowledge-config`: "Agent retrieval policy" 新增 planner opt-in;开启时被动检索经 planner(可对关系型 query 升级 graph),默认关时保持现有 hybrid/mode 行为。

## Impact

- **owning packages**:`fleetent.long_term_ctx`(`_search_knowledge` 按 policy 选 planner 或 search)+ `fleetent.agent_config`(`retrieval_policy` 新增字段)。
- **public API surface**:`AgentRetrievalPolicy` 新增 `use_planner` 字段(默认 false);`_search_knowledge` 内部分支,无对外签名变更。
- **owned tables**:无(配置在 agent.yaml,运行时读快照)。
- **config namespace**:`knowledge.retrieval_policy.use_planner`。
- **cross-module 依赖**:`long_term_ctx` 调 `knowledge_base` 既有 planner public API(`plan_knowledge_search` / `execute_knowledge_search_plan`),依赖方向不变;保持 agent ✗→ platform。
- **数据要求**:planner 升级 graph 仅在图谱有数据时返回 graph 结果——依赖 D3(`kb-extraction-auto-enqueue`)填图;无图数据时 planner 自然回落 hybrid,行为安全。
- **测试**:unit(policy 字段默认 false / 解析)+ integration(开启 → 关系型 query 经 planner 命中 graph 证据;默认关 → 走 search 不变)。
