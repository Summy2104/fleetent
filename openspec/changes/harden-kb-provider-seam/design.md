## Context

post-A+ 的 `_search_knowledge`(long_term_ctx/__init__.py:623-667):若有注入 provider 则 `_knowledge_provider(user_id, query, agent_id, limit)`(松契约,丢 tenant/kb_ids/audit,返回 list[object]);否则本地 fallback——解析 `agent.knowledge`(enabled/bindings→kb_ids、tenant)、读 `retrieval_policy`(use_planner/mode/rerank)、跑 `plan+execute` 或 `search`,返回 KnowledgeChunk。外层 `build_context` 已用 `_retrieve_with_timeout("knowledge", ..., empty=[])` 包裹检索路径。`Principal(user_id, tenant_id)` 定义于 identity.py;`KnowledgeChunk` 定义于 knowledge_base/core/models.py。本 change 是 Tier-2 的 keystone(Slice 1),后续 Slice 2(外部 provider)/ Slice 3(远程 KB 服务 + node 在 agent 进程注入)挂其上。

## Goals / Non-Goals

**Goals:**
- 正式化 KnowledgeProvider 契约(principal/kb_ids/audit 入参 + KnowledgeChunk 返回 + 失败降级)。
- 把本地逻辑抽成默认 LocalKnowledgeProvider,行为零变化。
- 作用域解析留 long-term-ctx,经契约传入 provider。

**Non-Goals:**
- 不实现远程 KB 服务(Slice 3)、外部/HTTP provider(Slice 2)。
- 不把真实 Principal 端到端贯穿 build_context(本 change 在 long-term-ctx 内重建 Principal(user_id, tenant_id))。
- 不改 retrieval_policy 字段、planner/search/knowledge_base 行为。
- 不改 build_context 对外签名。

## Decisions

### 决策:契约携带 scope+identity+audit,不携带 policy
- `(principal, query, kb_ids, limit, audit) → list[KnowledgeChunk]`。policy(mode/use_planner/rerank)是"怎么查",由各 provider 自行消化:LocalKnowledgeProvider 内部读 `agent.knowledge.retrieval_policy`;远程/外部 provider 自带 ranking。
- **为什么**:scope(查哪些 KB、谁在查)是 fleetent 的决策,必须传;policy 是实现细节,放进契约会绑死所有 provider 用 fleetent 的检索语义,违背"可换 provider"。

### 决策:scope 解析留在 long-term-ctx,provider 只收解析后的 kb_ids
- `_search_knowledge` 负责:enabled 检查、bindings→kb_ids、tenant 解析、构造 `Principal(user_id, tenant_id)`、空范围短路(不调 provider)。然后调 provider。
- **为什么**:所有 provider 共享同一套作用域/绑定语义,避免每个 provider 各自实现绑定解析(尤其外部 provider 不懂 fleetent 绑定模型)。LocalKnowledgeProvider 从"自己解析 scope"退化为"接收 scope"。

### 决策:默认 LocalKnowledgeProvider 始终存在,注入覆盖
- 启动期(或模块级)设默认 LocalKnowledgeProvider;`set_knowledge_provider` 注入则覆盖。`_search_knowledge` 永远走"解析 scope → 调当前 provider",不再有"provider 分支 + 本地分支"两套逻辑。
- **为什么**:消除两套分支漂移;本地也走契约,保证契约对本地/远程/外部一致可测。

### 决策:失败降级复用既有 timeout 框架,确认覆盖异常
- provider 调用已被 `_retrieve_with_timeout(empty=[])` 包裹。本 change 确认它对 provider **抛异常**(不止超时)也降级为空并记日志(若当前只捕超时则补捕异常)。

### 决策:Principal 在 long-term-ctx 内重建,完整贯穿后置
- build_context 当前只收 `user_id: str`;tenant 从 `agent.knowledge.tenant_id`(绑定解析)取。重建 `Principal(user_id, tenant_id)` 足够喂契约。把 loop.py 的真实 Principal 端到端穿过 build_context 是更大改动,留后续(Open Question)。

## Risks / Trade-offs

- **[行为漂移]** 抽 LocalKnowledgeProvider 时不慎改了检索行为。**Mitigation**:抽取前后对照——default provider 必须与现 `_search_knowledge` 本地分支逐行等价;integration 对照基线断言相同结果。
- **[契约变更波及下游]** 返回类型 list[object]→list[KnowledgeChunk] 与入参变更。**Mitigation**:下游 `_knowledge_source`/`_knowledge_candidate` 本就 duck-type KnowledgeChunk 字段,兼容;改注解 + 默认 provider 返回 KnowledgeChunk 即可。
- **[失败语义回归]** 若现有 timeout 框架只捕超时不捕异常,注入 provider 抛错可能冒泡。**Mitigation**:task 显式测"provider 抛异常 → 降级空",必要时在 _retrieve_with_timeout 或 provider 调用处补 try/except。
- **[与 E1 刚落地的代码]** E1 刚加了 planner 分支。**Mitigation**:本 change 从 post-A+ main 出发,把 planner+search 两分支一起搬进 LocalKnowledgeProvider。

## Migration Plan

- 纯检索路径重构 + 契约定义,无 schema、无配置变更。部署即生效,默认行为不变。回滚还原代码。

## Open Questions

- 把 loop.py 的真实 `Principal` 端到端贯穿 `build_context`(替代重建)——更干净但更大,作为后续小改评估,不阻塞本 keystone。
