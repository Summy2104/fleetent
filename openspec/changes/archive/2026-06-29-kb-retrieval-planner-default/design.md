## Context

`long_term_ctx._search_knowledge`(F1 `kb-binding-reconcile` 刚改过此函数,已落地 main)读 agent.yaml bindings 后调 `knowledge_base.search(mode=kb.retrieval_policy.mode)`。planner(`plan_knowledge_search` / `execute_knowledge_search_plan`)已存在且 `execute` 返回 `list[KnowledgeChunk]`(内部已归一化 hybrid + graph fill),但零生产调用。本 change 把被动检索按 policy opt-in 接到 planner,激活图谱查询(A+ 的检索侧)。填图谱由 D3(`kb-extraction-auto-enqueue`)负责。

## Goals / Non-Goals

**Goals:**
- `retrieval_policy.use_planner`(默认 false)opt-in;开启时被动检索经 planner,关系型 query 升级 graph。
- 默认行为与当前完全一致。

**Non-Goals:**
- 不改 planner / graph_search / search() 底层 API 行为(只接线,不改实现)。
- 不做 agent 主动 KB 工具(那是包 B,已否决)。
- 不改 long-term-ctx 预算/选择/注入语义。

## Decisions

### 决策:在 `_search_knowledge` 内按 policy 二选一,planner 返回 KnowledgeChunk 直接复用现有管线
- `use_planner` 真 → `plan_knowledge_search(query, options)` + `execute_knowledge_search_plan(plan)`;假 → 现有 `search(mode=...)`。两者都返回 `list[KnowledgeChunk]`,下游 `_knowledge_candidate` / ContextSource / 预算逻辑不变。
- **为什么小改**:planner execute 已归一化为 KnowledgeChunk,无需 GraphSearchChunk → ContextSource 适配器。
- **替代**:把 planner 设成默认(无开关)。否决——graph 增延迟、且仅在图谱有数据时有价值,opt-in 更稳、默认零回归。

### 决策:默认 false,opt-in
- 保持现有 hybrid 行为为默认;想要图谱的 agent 显式开。无图数据时 planner 自然回落 hybrid,开了也安全。

### 决策:与 D3 解耦但互补
- E1 不依赖 D3 落地即可合入(默认 false,行为不变;开启且无图数据时 planner 回落 hybrid)。真正产生 graph 价值需 D3 填图。两者可并行开发,E1 测试用 fixture 直接铺图谱,不依赖 D3。

## Risks / Trade-offs

- **[graph 延迟]** 关系型 query 多走一次 graph_search。**Mitigation**:planner 规则只对 entity/relation-like query 升级,普通 query 仍 hybrid;opt-in 限定到需要的 agent。
- **[patch 陷阱]** 改 `_search_knowledge` 测试时,monkeypatch 须指真实子模块(`fleetent.long_term_ctx` 的 knowledge 调用),patch 旧 shim 不生效(AGENTS gotcha)。**Mitigation**:测试按现有 long_term_ctx patch 约定写。
- **[与 F1 同函数]** F1 刚改过 `_search_knowledge`(单租户 tenant)。F1 已 merge main,本 change 从最新 main 出发,无并行冲突。

## Migration Plan

- 纯行为接线 + 配置字段,无 schema。`use_planner` 默认 false → 存量 agent 行为不变。部署即生效(开启 agent 下个 session 用 planner,符合 F1 的 session 边界 reload)。回滚还原代码。

## Open Questions

- planner 的 `KnowledgeSearchOptions`(top_k / rerank)如何从 `retrieval_policy` 映射:实现期对齐既有字段,不新增语义。
