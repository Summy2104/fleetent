# kb-admin-api Specification

## Purpose
TBD - created by archiving change 2026-06-02-knowledge-base-management. Update Purpose after archive.
## Requirements
### Requirement: Knowledge base listing
The system SHALL list all knowledge bases in the current tenant via `/admin/kb`, each showing kb_id, description, document count, chunk count, last import time, bound agents, and vector namespace overview. The list SHALL support search and sort by kb_id / description. Listing SHALL be available to both viewer and admin.

#### Scenario: List shows KB metadata
- **WHEN** an admin or viewer opens the knowledge base list in the current tenant
- **THEN** each KB shows kb_id, description, document/chunk counts, last import time, and the agents bound to it

#### Scenario: Archived KBs are distinguished
- **WHEN** a KB has been archived
- **THEN** the list marks it as archived and excludes it from recall and from the bindable list

### Requirement: Create knowledge base

An admin SHALL be able to create a KB via `/admin/kb` with a tenant-unique kb_id and a description. kb_id uniqueness is scoped to (tenant_id, kb_id). The created KB SHALL be usable without restarting the service.

#### Scenario: Create KB without restart (场景 103)
- **WHEN** an admin creates kb_id "support" in a tenant that has no such KB
- **THEN** the KB is created successfully and becomes available for later document lifecycle, retrieval, evaluation, and binding operations without a service restart

#### Scenario: Duplicate kb_id is rejected (场景 104)
- **WHEN** kb_id "support" already exists in the current tenant and an admin creates "support" again
- **THEN** the request is rejected with "kb_id already exists" and nothing is written to the database

#### Scenario: Viewer cannot create
- **WHEN** a viewer attempts to create a KB
- **THEN** the request returns 403

### Requirement: Edit knowledge base
An admin SHALL be able to edit a KB's description. kb_id SHALL NOT be renamed in place.

#### Scenario: Edit description is audited
- **WHEN** an admin updates a KB's description
- **THEN** the change is persisted and an audit entry (`kb_edit`) is written

### Requirement: Archive knowledge base with binding protection
KB deletion SHALL be a soft delete (archive): documents, chunks, vectors, and history are retained; the KB no longer participates in recall and is hidden from the bindable list. Archive SHALL be blocked when the KB is still bound to any agent.

#### Scenario: Archive blocked by agent binding (场景 106)
- **WHEN** a KB is still bound to agent "support-bot" and an admin attempts to delete it
- **THEN** the deletion is blocked, the binding agents are listed, the admin is told to unbind first, and nothing is written

#### Scenario: Archive after unbind retains data
- **WHEN** a KB has no agent bindings and an admin archives it
- **THEN** the KB is archived, its documents and chunks are retained, and an audit entry (`kb_archive`) is written

### Requirement: Document list and lifecycle

The system SHALL list documents within a single KB (filename, source / source_url, chunk count, created time), allow previewing a document's chunks (content + section context), and allow deleting a single document. Deletion SHALL cascade to chunks and vector entries via the engine `delete(document_id)`.

#### Scenario: Document list reflects KB-hosted content
- **WHEN** a document already exists in the KB
- **THEN** `GET /admin/kb/{kb_id}/documents` returns that document with its real chunk count and source metadata

#### Scenario: Chunk preview shows section context
- **WHEN** an admin or viewer previews a document
- **THEN** each chunk shows its content and section context

#### Scenario: Delete cascades and is audited (场景 107)
- **WHEN** an admin deletes document D in a KB and confirms
- **THEN** D and its chunks and vector entries are removed via the engine, subsequent retrieval no longer returns D's content, and the deletion is audited (`doc_delete`)

### Requirement: Per-KB observation aggregation
KB detail 视图 SHALL 呈现按 kb 聚合的**检索 proxy 指标**，数据源为 observability 域的 `kb_retrieval` trace（③ kb-retrieval-audit 所写）；本平面只按 kb 聚合、read-only、不改 index。指标 SHALL 包含：**延迟 p50/p95、空召回率（命中 0 条的占比）、score 分布、query/hit 计数**，可下钻到引用的 session traces。

**线上 SHALL NOT 声称给出真实 recall**：真实 recall@k/MRR 需 ground-truth 标注，只能在离线评估（`/evaluations`）算；observation 平面只给无需标注的 proxy 指标（原占位字段 `recall_hits` 的"recall"语义被纠正为 proxy）。citation 率因当前无 citation 数据而暂不在本平面提供。

#### Scenario: Per-KB proxy 指标只读聚合
- **WHEN** admin 打开某 KB 的 observation 视图
- **THEN** 展示从 `kb_retrieval` trace 聚合的延迟 p50/p95、空召回率、score 分布、计数（不修改 index），可下钻引用 session

#### Scenario: 空召回也被计入
- **WHEN** 该 KB 有命中 0 条的检索
- **THEN** 空召回率指标反映这些 0 命中（来自 ③ 留痕的空召回事件）

#### Scenario: 不在线上谎报真 recall
- **WHEN** observation 视图展示指标
- **THEN** 不出现需 ground-truth 的真实 recall@k/MRR（那归 /evaluations）；只展示 proxy 指标

### Requirement: Knowledge base management permissions and audit
KB / document creation, deletion, archive, and agent binding SHALL be admin-only. Viewers SHALL only browse KBs, documents, and retrieval test results. High-risk actions (delete KB, delete document) SHALL require a second confirmation. All write operations SHALL be audited.

#### Scenario: Viewer cannot manage knowledge bases (场景 108)
- **WHEN** a viewer opens the knowledge base management page and tries to create a KB or delete a document
- **THEN** the controls are hidden or the request returns 403, and the viewer may only browse KBs, documents, and retrieval test results

#### Scenario: Write operations are audited
- **WHEN** an admin performs any KB or document write operation
- **THEN** an audit entry recording actor / action / target / detail is written

### Requirement: KB 数据面经中心 kb-serve 客户端

平台 `/admin/kb/*` 的 **KB 数据面操作**(列/建/改/归档 KB、文档列/预览 chunk/删文档、检索、离线评估)SHALL 经**中心 kb-serve 的 HTTP 客户端**执行,SHALL NOT 进程内直读写 KB 库——以支持平台与 KB 分机部署(平台 1:1 于 KB 但可异机)。平台 SHALL 持中心 kb-serve URL(平台配置)与共享 service key(引用),每次调用为目标租户 mint `X-Fleetent-Principal` + Bearer 共享 key;因 kb-serve 多租户,平台打**一个 URL**、tenant 靠 principal 路由。

`/admin/kb/search` SHALL 经 kb-serve 检索,支持 `rerank` / `use_planner` 透传,请求/响应契约对齐 kb-serve(`limit`、KnowledgeChunk 形状)。

绑定(`/admin/kb/{id}/agents`、`/admin/agents/{name}/kbs`,agent_kbs @ management.db)与 per-KB `observation`(需 bound_agent_ids + 跨 agent 检索 trace)SHALL 仍由平台 in-process 承载,不经 kb-serve(kb-serve 无 agent/绑定/trace 概念)。平台入口鉴权(session + viewer/admin RBAC)SHALL 保持在平台层,通过后再以服务身份调 kb-serve。

#### Scenario: 平台数据面经 kb-serve
- **WHEN** admin 经平台 `/admin/kb` 列/建/改/归档 KB 或列/删文档或检索
- **THEN** 平台经中心 kb-serve HTTP 客户端执行(带共享 key + 为该租户 mint 的 principal),不进程内直读 KB 库
- **AND** 平台与 KB 分机时仍可用

#### Scenario: search 透传质量参数并对齐契约
- **WHEN** `/admin/kb/search` 带 `rerank=true` 或 `use_planner=true`
- **THEN** 平台经 kb-serve 检索、返回对齐 kb-serve 的 KnowledgeChunk 结果(不再是无 rerank/planner 的缩水子集)

#### Scenario: 绑定与 observation 仍平台自持
- **WHEN** 审视绑定端点与 `/admin/kb/{id}/observation`
- **THEN** 它们仍由平台 in-process 承载(agent_kbs @ management.db / 跨 agent trace 聚合),不经 kb-serve

