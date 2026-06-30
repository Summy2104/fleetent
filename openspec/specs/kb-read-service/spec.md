# kb-read-service Specification

## Purpose
为每个租户提供一个只读 HTTP KB 服务，实现 `kb-http-provider` 的 wire 协议，使 agent 可经远程 `HttpKnowledgeProvider` 检索同租户 `kb/` 数据，而不搬迁 ingest 路径。
## Requirements
### Requirement: KB read service implements the knowledge wire protocol

系统 SHALL 提供一个 HTTP KB 读服务,实现 `kb-http-provider` 定义的中立 wire 协议:`POST /search` 接收 `{principal:{user_id, tenant_id}, query, kb_ids, limit}`,并 MAY 接收可选检索策略 `mode` / `rerank` / `use_planner`,返回 `{chunks: [KnowledgeChunk JSON]}`。服务 SHALL 经 `knowledge_base` public API(`search` / `plan_knowledge_search`+`execute` / `graph_search`)产出结果,SHALL NOT 复制检索逻辑。

#### Scenario: Search request returns chunks
- **WHEN** 收到合法 `POST /search` 请求
- **THEN** 服务调用 `knowledge_base` 检索,返回 `{chunks: [...]}`,每个 chunk 含 KnowledgeChunk 字段(id/document_id/tenant_id/kb_id/filename/content/position/score/source/source_url/metadata)
- **AND** 响应可被 `HttpKnowledgeProvider` 反序列化为 `list[KnowledgeChunk]`

#### Scenario: 缺省策略向后兼容
- **WHEN** 请求未带 `mode`/`rerank`/`use_planner`
- **THEN** 服务以服务级默认 `mode`、`rerank=False`、`use_planner=False` 检索(与扩展前行为一致)

### Requirement: Per-tenant scoping bound at boot

服务 SHALL 是 per-tenant 进程:启动时绑定一个 `tenant_id`,经 `tenant_scope(tenant_id)` 注入 `kb_db` 与 `kb_vector_backend` 一次。服务 SHALL 只读该租户的 `tenants/<tenant>/kb/data/`,物理上够不到其它租户的库。

#### Scenario: Boot binds tenant scope once
- **WHEN** 服务以 `tenant_id=T` 启动
- **THEN** 经 `tenant_scope(T)` 注入 KB 关系库与向量后端,只读 `tenants/T/kb/data/`

#### Scenario: Mismatched tenant is rejected
- **WHEN** 请求的 `principal.tenant_id` 与服务绑定的租户不一致
- **THEN** 服务拒绝该请求(不跨租户检索)

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

### Requirement: Service authentication

服务 SHALL 用 Bearer service key 鉴权,并经 `X-Fleetent-Principal`(`identity.decode_ingress_principal`)解析请求主体。缺失或非法鉴权 SHALL 被拒绝。

#### Scenario: Valid service key and principal pass
- **WHEN** 请求带合法 Bearer service key 与可解析的 `X-Fleetent-Principal`
- **THEN** 服务受理并按解析出的 principal/tenant 处理

#### Scenario: Missing auth is rejected
- **WHEN** 请求缺 Bearer key 或 `X-Fleetent-Principal` 不可解析
- **THEN** 服务拒绝该请求

### Requirement: Read service does not own ingest

本服务 SHALL 只读 `kb/data/`,SHALL NOT 改变现有 ingest(worker / 队列 / connector secret)。KB 数据由现有 ingest 写入,服务读取同主机的 `tenants/<tenant>/kb/data/`。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: Service is read-only over kb/data/
- **WHEN** 检视服务实现
- **THEN** 服务只读 `tenants/<tenant>/kb/data/` 下的库,不写入,也不改 ingest 队列/worker/connector secret
- **AND** 服务进程不 `import fleetent.platform.*`

