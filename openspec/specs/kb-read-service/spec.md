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

本服务 SHALL NOT 拥有 **ingest 管线**:切块 / embedding / 向量入库等**内容与向量写**唯一经 kb-worker(队列消费),本服务 SHALL NOT 改变 ingest(worker / 队列 / connector secret)、SHALL NOT 承载 connector sweep 调度(归 kb-worker)。本服务 MAY 承载 KB **元数据 / 生命周期管理**(建库 / 归档 / 改描述 / 切换 extraction / 删文档)与只读管理 / 评估端点——这些经 `knowledge_base` 模块公共函数直接作用于本租户 `tenants/<tenant>/kb/data/`,与 `fleetent kb create` CLI 及平台 `/admin/kb` 的既有直接写同类,不触碰 ingest 管线。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: 不拥有 ingest 管线,但可管理元数据
- **WHEN** 检视服务实现
- **THEN** 内容 / 向量写(切块 / embedding / 向量入库)不在本服务内发生,仍唯一经 kb-worker;本服务不改 ingest 队列 / worker / connector secret、不承载 sweep
- **AND** 本服务可经 `knowledge_base` 公共函数执行 KB 元数据 / 生命周期管理与只读管理 / 评估
- **AND** 服务进程不 `import fleetent.platform.*`

### Requirement: KB 服务状态只读端点

kb-serve SHALL 提供只读 `GET /status`,暴露本租户的 connector 同步状态与近期 ingest job 状态(含 status / 结果摘要),供运维观测 ingest 进度与失败原因。鉴权 SHALL 与 `/search` 一致(Bearer service key + ingress principal,principal.tenant_id 须与服务绑定租户一致)。kb-serve SHALL 为纯读服务,SHALL NOT 承载 connector sweep 调度(调度归 kb-worker,见 `kb-standalone-ingest`)。

#### Scenario: 查询连接器与 job 状态
- **WHEN** 运维以合法 Bearer + principal 请求 `GET /status`
- **THEN** 返回本租户 connector 状态(来自 `knowledge_connector_status`)与近期 ingest job(来自 `kb_ingest_jobs`,含 status 与结果摘要)
- **AND** 跨租户(principal.tenant_id ≠ 绑定租户)被拒绝

#### Scenario: kb-serve 不承载 sweep
- **WHEN** 只启动 kb-serve(未启动 kb-worker)
- **THEN** kb-serve 提供检索与状态读取,但不运行 connector sweep 调度

### Requirement: KB 管理端点

kb-serve SHALL 暴露本租户 KB 的管理端点,全复用 `knowledge_base` 模块公共函数、单租户(绑 `config.tenant_id`),鉴权与 `/search` 一致(Bearer service key + ingress principal,principal.tenant_id 须等于绑定租户,跨租户拒绝):

- `POST /kb`(建库)、`GET /kb`(列 KB)、`PATCH /kb/{kb_id}`(改描述 / 切换 extraction)、`DELETE /kb/{kb_id}`(归档)。
- `GET /kb/{kb_id}/documents`(列文档)、`GET /kb/{kb_id}/documents/{document_id}/chunks`(预览 chunk)、`DELETE /kb/{kb_id}/documents/{document_id}`(删文档)。

绑定(KB↔agent)SHALL NOT 由 kb-serve 承载(依赖 management.db 与 agent 身份,归平台)。per-KB observation 指标 SHALL NOT 由 kb-serve 承载(依赖绑定 agent 集与跨 agent 检索 trace,归平台)。

#### Scenario: 建库并管理文档(无 platform)
- **WHEN** 以合法 Bearer + principal 请求 `POST /kb` 建库,再 `GET /kb`、`GET /kb/{kb_id}/documents`
- **THEN** KB 在本租户 `kb.db` 创建,列表 / 文档端点返回本租户对应数据
- **AND** 全程不依赖 platform 或 management.db、服务不 import platform

#### Scenario: 删文档
- **WHEN** `DELETE /kb/{kb_id}/documents/{document_id}`
- **THEN** 经 `knowledge_base` 公共删除函数移除该文档及其 chunk(元数据 / 生命周期写,不经 ingest 管线)

#### Scenario: 跨租户拒绝
- **WHEN** principal.tenant_id ≠ 服务绑定租户
- **THEN** 管理端点返回 403(与 /search、/status 一致)

### Requirement: 离线评估端点

kb-serve SHALL 暴露 `POST /evaluations`,经 `knowledge_base` 检索评估公共 API 对本租户 KB 运行离线检索评估并返回结果,单租户、鉴权与 /search 一致。评估 SHALL NOT 依赖 platform 或 agent 绑定(纯 KB 侧检索质量度量)。

#### Scenario: 运行离线评估
- **WHEN** 以合法 Bearer + principal 请求 `POST /evaluations`(含评估用例)
- **THEN** 服务经 `knowledge_base` 评估 API 运行并返回评分结果,不依赖 platform

