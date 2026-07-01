## MODIFIED Requirements

### Requirement: KB read service implements the knowledge wire protocol

系统 SHALL 提供一个 HTTP KB 读服务,实现 `kb-http-provider` 定义的中立 wire 协议:`POST /search` 接收 `{principal:{user_id, tenant_id}, query, kb_ids, limit}`,并 MAY 接收可选检索策略 `mode` / `rerank` / `use_planner`,返回 `{chunks: [KnowledgeChunk JSON]}`。服务 SHALL 经 `knowledge_base` public API(`search` / `plan_knowledge_search`+`execute` / `graph_search`)产出结果,SHALL NOT 复制检索逻辑。

#### Scenario: Search request returns chunks
- **WHEN** 收到合法 `POST /search` 请求
- **THEN** 服务调用 `knowledge_base` 检索,返回 `{chunks: [...]}`,每个 chunk 含 KnowledgeChunk 字段(id/document_id/tenant_id/kb_id/filename/content/position/score/source/source_url/metadata)
- **AND** 响应可被 `HttpKnowledgeProvider` 反序列化为 `list[KnowledgeChunk]`

#### Scenario: 缺省策略向后兼容
- **WHEN** 请求未带 `mode`/`rerank`/`use_planner`
- **THEN** 服务以服务级默认 `mode`、`rerank=False`、`use_planner=False` 检索(与扩展前行为一致)

### Requirement: Service-level retrieval policy

服务 SHALL 按**请求携带的检索策略**执行,而非把质量钉在裸 hybrid:`mode` 取自请求(缺省为服务级默认 `hybrid`);`rerank` 取自请求(缺省 `False`),SHALL NOT 硬编码为 `False`;`use_planner` 取自请求(缺省 `False`),为真时 SHALL 经 `plan_knowledge_search` + `execute_knowledge_search_plan` 执行(与 Local provider 的 planner 路径一致),否则以 `mode` + `rerank` 调用 `knowledge_base.search`。`kb_ids` 与 `limit` 取自请求。服务 SHALL NOT 依赖某个 "active agent" 全局来决定核心检索策略。

#### Scenario: 请求的 mode/rerank 被执行
- **WHEN** 请求带 `mode=hybrid` 且 `rerank=true`
- **THEN** 服务以 hybrid + rerank 调用 `knowledge_base.search`(不再硬编码 `rerank=False`)

#### Scenario: 请求开启 planner
- **WHEN** 请求带 `use_planner=true`
- **THEN** 服务经 `plan_knowledge_search` + `execute_knowledge_search_plan` 执行(可含 graph 升级),返回融合结果
- **AND** 不依赖 `agent_config.active_agent_or_default()` 决定策略

#### Scenario: rerank 仅 hybrid
- **WHEN** 请求 `rerank=true` 但 `mode` 非 hybrid
- **THEN** 沿用 `knowledge_base.search` 既有约束(rerank 仅支持 hybrid),以一致方式报错或忽略,不静默产出错误结果
