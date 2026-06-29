## Why

`long_term_ctx` 的 KB 检索源是经 `set_knowledge_provider` 注入的可替换缝,但当前**松且休眠**:契约是 `(user_id, query, agent_id, limit) → list[object]`——丢了 tenant、丢了完整身份、不传 audit、返回无类型、没有失败语义,且全 src 零注入。这道缝是"多 node 远程 KB"与"换检索源(外部/BYO RAG)"两个已确认的近期需求的**同一根地基**:两者在代码上都只是给这道缝注入一个非默认 provider。本 change 把缝做硬(keystone),为后续两类 provider 打地基,且**默认行为零变化**。

## What Changes

- **正式化 `KnowledgeProvider` 契约**:`(principal: Principal, query: str, kb_ids: list[str], limit: int, audit: KBRetrievalAuditContext | None) → list[KnowledgeChunk]`。携带完整身份(principal 含 tenant)、fleetent 解析好的作用域(kb_ids)、审计上下文;正式返回类型替代 `list[object]`。
- **抽出默认 `LocalKnowledgeProvider`**:把现有本地检索逻辑(读 agent 的 retrieval_policy、跑 hybrid / planner、返回 KnowledgeChunk)抽成一个显式的默认 provider,行为与现状完全一致。
- **作用域在 long-term-ctx 解析后传给 provider**:`enabled` / bindings → kb_ids / tenant / principal 的解析留在 long-term-ctx(provider-agnostic),解析结果经契约传入;provider 只在该范围内检索。**policy(mode/use_planner/rerank)不进契约**——由各 provider 自行消化(LocalKnowledgeProvider 内部读 agent 配置)。
- **失败优雅降级**:provider 超时或抛错 → 记日志返回空,不中断 `build_context`(正式化既有 `_retrieve_with_timeout(empty=[])` 行为,确认覆盖异常而非仅超时)。
- **注入替换默认**:`set_knowledge_provider` 注入的 provider 替换默认 LocalKnowledgeProvider,并按硬契约接收完整入参。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `long-term-ctx`: 正式化 knowledge provider 契约(principal/kb_ids/audit 入参 + KnowledgeChunk 返回 + 失败降级);默认 built-in provider 抽成显式 LocalKnowledgeProvider;作用域由 long-term-ctx 解析后经契约传入 provider。

## Impact

- **owning package**:`fleetent.long_term_ctx`(契约定义、`_search_knowledge` 重构、LocalKnowledgeProvider)。复用 `fleetent.identity.Principal`、`fleetent.knowledge_base.KnowledgeChunk`。
- **public API surface**:`KnowledgeProvider` 类型签名变更(扩入参 + 收紧返回);`set_knowledge_provider` 不变;`_search_knowledge` 内部重构,`build_context` 对外不变。
- **owned tables**:无(纯检索路径重构)。
- **config namespace**:无(policy 仍读 `knowledge.retrieval_policy`,无新增字段)。
- **cross-module 依赖**:保持 `long_term_ctx` ✗→ `platform`;注入式 provider 由外部(server.py / 未来 node 在 agent 进程)注入,不被 long_term_ctx import,护栏不破。
- **行为**:默认 LocalKnowledgeProvider 与当前 `_search_knowledge` 完全等价,**零回归**。
- **明确不做(后续切片)**:远程 KB 服务(Slice 3)、HTTP/外部 provider 实现(Slice 2)、把真实 Principal 端到端贯穿 `build_context`(本 change 在 long-term-ctx 内重建 `Principal(user_id, tenant_id)`,完整贯穿留后续)。
- **测试**:unit/integration(默认行为不变;注入 provider 收到完整 scope/principal/audit;provider 抛错/超时降级空)。
