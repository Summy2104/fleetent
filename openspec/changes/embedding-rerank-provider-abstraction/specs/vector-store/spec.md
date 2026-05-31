## MODIFIED Requirements

### Requirement: Vector store configuration
系统 SHALL 提供 vector store、embedding 和 rerank 配置默认值。当前版本 SHALL 默认使用
in-memory vector backend、deterministic embedding backend，并默认禁用 rerank。

#### Scenario: Default embedding config
- **WHEN** 未显式配置 embedding
- **THEN** `embedding.backend` 默认为 `deterministic`
- **AND** `embedding.dimensions` 默认为 64

#### Scenario: HTTP embedding config exists
- **WHEN** 读取默认 settings
- **THEN** embedding 配置包含 endpoint、model、api_key_env 和 timeout_seconds 字段

#### Scenario: Default rerank config
- **WHEN** 未显式配置 rerank
- **THEN** `rerank.backend` 默认为 `disabled`

#### Scenario: HTTP rerank config exists
- **WHEN** 读取默认 settings
- **THEN** rerank 配置包含 endpoint、model、api_key_env 和 timeout_seconds 字段

#### Scenario: Unsupported provider backend fails fast
- **WHEN** 配置了当前不支持的 vector、embedding 或 rerank backend
- **THEN** 初始化失败，并明确说明当前支持的 backend

## ADDED Requirements

### Requirement: Embedding provider abstraction
系统 SHALL 提供可替换的 embedding provider，用于将文本转换为向量。

#### Scenario: Deterministic embedding remains default
- **WHEN** 使用默认配置创建 embedding provider
- **THEN** 系统使用 deterministic embedding provider

#### Scenario: HTTP embedding provider can be configured
- **WHEN** `embedding.backend="http"`
- **THEN** 系统创建 HTTP embedding provider

#### Scenario: HTTP embedding request shape
- **WHEN** HTTP embedding provider embed 非空文本
- **THEN** 系统向 configured endpoint 发送包含 model 和 input list 的请求
- **AND** `api_key_env` 非空且对应环境变量存在时发送 Authorization Bearer header

#### Scenario: HTTP embedding response shape
- **WHEN** HTTP embedding provider 收到 `data[0].embedding`
- **THEN** 返回该 embedding vector
- **AND** vector 维度必须等于 `embedding.dimensions`

#### Scenario: Empty text embedding avoids HTTP call
- **WHEN** HTTP embedding provider embed 空白文本
- **THEN** 不发送 HTTP 请求
- **AND** 返回指定维度的零向量

#### Scenario: HTTP embedding errors are explicit
- **WHEN** HTTP embedding 返回非 2xx、超时、malformed JSON、缺失 embedding 或维度不匹配
- **THEN** 系统抛出明确的 embedding provider error
- **AND** 不静默 fallback 到 deterministic embedding

### Requirement: Rerank provider abstraction
系统 SHALL 提供可替换的 rerank provider，用于后续 knowledge-base retrieval 对候选文档重排。

#### Scenario: Rerank result shape
- **WHEN** 调用方收到 `RerankResult`
- **THEN** 结果只包含原始 document index 和 score

#### Scenario: Rerank is disabled by default
- **WHEN** 使用默认 rerank 配置创建 provider
- **THEN** 系统创建 disabled rerank provider
- **AND** 调用 rerank 时明确失败

#### Scenario: Deterministic rerank provider exists for tests
- **WHEN** `rerank.backend="deterministic"`
- **THEN** 系统创建 deterministic rerank provider
- **AND** 相同输入返回稳定结果

#### Scenario: HTTP rerank request shape
- **WHEN** HTTP rerank provider rerank documents
- **THEN** 系统向 configured endpoint 发送 model、query、documents 和 top_n
- **AND** `api_key_env` 非空且对应环境变量存在时发送 Authorization Bearer header

#### Scenario: HTTP rerank response shape
- **WHEN** HTTP rerank provider 收到 `results[{index, score}]`
- **THEN** 返回按 provider 输出顺序排列的 `RerankResult`

#### Scenario: HTTP rerank errors are explicit
- **WHEN** HTTP rerank 返回非 2xx、超时、malformed JSON、越界 index 或非数字 score
- **THEN** 系统抛出明确的 rerank provider error
- **AND** 不静默 fallback 到 deterministic rerank

### Requirement: Vector store runtime uses embedding provider
`vector_store.upsert()` 和 `vector_store.search()` SHALL 使用配置的 embedding provider，
但 public API 保持不变。

#### Scenario: Upsert embeds through configured provider
- **WHEN** 调用 `vector_store.upsert(id, text, namespace)`
- **THEN** 系统通过配置的 embedding provider 生成向量
- **AND** 将向量写入 vector backend

#### Scenario: Search embeds through configured provider
- **WHEN** 调用 `vector_store.search(query, namespace, limit)`
- **THEN** 系统通过配置的 embedding provider 生成 query 向量
- **AND** 使用该向量查询 vector backend
