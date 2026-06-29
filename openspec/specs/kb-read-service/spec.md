# kb-read-service Specification

## Purpose
为每个租户提供一个只读 HTTP KB 服务，实现 `kb-http-provider` 的 wire 协议，使 agent 可经远程 `HttpKnowledgeProvider` 检索同租户 `kb/` 数据，而不搬迁 ingest 路径。
## Requirements
### Requirement: KB read service implements the knowledge wire protocol

系统 SHALL 提供一个 HTTP KB 读服务,实现 `kb-http-provider` 定义的中立 wire 协议:`POST /search` 接收 `{principal:{user_id, tenant_id}, query, kb_ids, limit}`,返回 `{chunks: [KnowledgeChunk JSON]}`。服务 SHALL 经 `knowledge_base` public API(`search` / `plan_knowledge_search`+`execute` / `graph_search`)产出结果,SHALL NOT 复制检索逻辑。

#### Scenario: Search request returns chunks
- **WHEN** 收到合法 `POST /search` 请求
- **THEN** 服务调用 `knowledge_base` 检索,返回 `{chunks: [...]}`,每个 chunk 含 KnowledgeChunk 字段(id/document_id/tenant_id/kb_id/filename/content/position/score/source/source_url/metadata)
- **AND** 响应可被 `HttpKnowledgeProvider` 反序列化为 `list[KnowledgeChunk]`

### Requirement: Per-tenant scoping bound at boot

服务 SHALL 是 per-tenant 进程:启动时绑定一个 `tenant_id`,经 `tenant_scope(tenant_id)` 注入 `kb_db` 与 `kb_vector_backend` 一次。服务 SHALL 只读该租户的 `tenants/<tenant>/kb/`,物理上够不到其它租户的库。

#### Scenario: Boot binds tenant scope once
- **WHEN** 服务以 `tenant_id=T` 启动
- **THEN** 经 `tenant_scope(T)` 注入 KB 关系库与向量后端,只读 `tenants/T/kb/`

#### Scenario: Mismatched tenant is rejected
- **WHEN** 请求的 `principal.tenant_id` 与服务绑定的租户不一致
- **THEN** 服务拒绝该请求(不跨租户检索)

### Requirement: Service-level retrieval policy

服务 SHALL 以显式 `mode`(服务级默认 `hybrid`)调用 `knowledge_base.search`,`kb_ids` 与 `limit` 取自请求。服务 SHALL NOT 依赖某个 "active agent" 全局来决定核心检索 mode。

#### Scenario: Explicit mode drives retrieval
- **WHEN** 服务处理检索请求
- **THEN** 以显式 `mode`(默认 hybrid)、请求的 `kb_ids`/`limit` 调用 `knowledge_base.search`
- **AND** 不依赖 `agent_config.active_agent_or_default()` 决定 mode

### Requirement: Service authentication

服务 SHALL 用 Bearer service key 鉴权,并经 `X-Fleetent-Principal`(`identity.decode_ingress_principal`)解析请求主体。缺失或非法鉴权 SHALL 被拒绝。

#### Scenario: Valid service key and principal pass
- **WHEN** 请求带合法 Bearer service key 与可解析的 `X-Fleetent-Principal`
- **THEN** 服务受理并按解析出的 principal/tenant 处理

#### Scenario: Missing auth is rejected
- **WHEN** 请求缺 Bearer key 或 `X-Fleetent-Principal` 不可解析
- **THEN** 服务拒绝该请求

### Requirement: Read service does not own ingest

本服务 SHALL 只读 `kb/`,SHALL NOT 改变现有 ingest(worker / 队列 / connector secret)。KB 数据由现有 ingest 写入,服务读取同主机的 `tenants/<tenant>/kb/`。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: Service is read-only over kb/
- **WHEN** 检视服务实现
- **THEN** 它只经 `knowledge_base` 读路径访问 `kb/`,不入队/不写 KB/不搬迁 ingest
- **AND** 不 import `fleetent.platform.*`
