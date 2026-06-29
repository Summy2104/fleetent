## MODIFIED Requirements

### Requirement: Optional knowledge provider
系统 SHALL 将 KB 检索作为可替换的 knowledge provider,经一个正式契约访问:
`(principal: Principal, query: str, kb_ids: list[str], limit: int, audit: KBRetrievalAuditContext | None) → list[KnowledgeChunk]`。
系统 SHALL 提供两个 built-in provider 实现:默认 `LocalKnowledgeProvider`(读本地 knowledge-base、按 agent retrieval_policy 跑检索),以及 `HttpKnowledgeProvider`(经 HTTP 调一个远程 KB 检索端点)。`HttpKnowledgeProvider` SHALL 按一份中立 wire 协议工作——请求体 `{principal:{user_id, tenant_id}, query, kb_ids, limit}`,响应体 `{chunks: [KnowledgeChunk JSON]}`——并以 Bearer service key + `X-Fleetent-Principal` header 鉴权(复用 `identity.encode_ingress_principal`);自家 KB 服务与外部系统实现同一份协议,无特权内部路径。
系统 SHALL 允许经 `set_knowledge_provider` 注入替换 provider,注入的 provider SHALL 按同一契约接收 principal、fleetent 解析好的 kb_ids 与 audit。knowledge provider 未启用、未配置、返回空结果、超时或抛错(含 HTTP 错误/网络故障)时,long-term-ctx 仍正常返回可用上下文(失败降级为空结果)。

#### Scenario: Knowledge provider disabled
- **WHEN** knowledge provider 未配置或被禁用
- **THEN** `build_context()` 不抛出异常
- **AND** 如果 memory 有结果，则正常返回 memory context

#### Scenario: Knowledge provider returns empty results
- **WHEN** knowledge provider 返回空结果
- **THEN** `BuiltContext.text` 不包含空的 knowledge 区段

#### Scenario: Knowledge results are included when available
- **WHEN** knowledge provider 返回相关 chunks
- **THEN** `BuiltContext.text` 包含 knowledge 区段
- **AND** `BuiltContext.sources` 包含 `source_type="knowledge"` 的来源摘要

#### Scenario: Default provider preserves current behavior
- **WHEN** 未注入自定义 provider 且 `knowledge_base.enabled=true`
- **THEN** long-term-ctx 经默认 `LocalKnowledgeProvider` 检索
- **AND** 结果与直接调用 `knowledge_base.search()` / planner(按 retrieval_policy)等价
- **AND** provider 返回的 source id 对应 chunk id

#### Scenario: Injected provider receives full scope
- **WHEN** 经 `set_knowledge_provider` 注入了自定义 provider
- **THEN** long-term-ctx 以 `(principal, query, kb_ids, limit, audit)` 调用它
- **AND** principal 含 tenant_id 与 user_id、kb_ids 为 fleetent 按 agent 绑定解析后的范围、audit 被透传
- **AND** 返回类型为 `list[KnowledgeChunk]`

#### Scenario: HttpKnowledgeProvider retrieves over the wire protocol
- **WHEN** 配置为 `HttpKnowledgeProvider` 且远程 KB 端点可用
- **THEN** provider 以 `{principal, query, kb_ids, limit}` POST 到配置的 endpoint,带 Bearer service key 与 `X-Fleetent-Principal` header
- **AND** 把响应 `{chunks: [...]}` 反序列化为 `list[KnowledgeChunk]` 返回给 long-term-ctx 预算管线

#### Scenario: Provider failure degrades to empty
- **WHEN** knowledge provider 超时或抛出异常(含 HttpKnowledgeProvider 的 HTTP 错误 / 网络故障)
- **THEN** long-term-ctx 记日志并将该路径降级为空结果
- **AND** `build_context()` 不抛出、不中断回复
