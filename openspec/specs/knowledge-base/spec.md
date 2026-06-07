# knowledge-base Specification

## Purpose
Provide tenant-scoped enterprise document ingestion, parsing, indexing, retrieval, local source sync,
and retrieval evaluation for agent long-term context.
## Requirements
### Requirement: KnowledgeBridge migration plan
系统 SHALL 保留 `knowledge-bridge` 到 fleetent 的历史迁移计划，作为后续知识库增强的参考资料。

#### Scenario: Migration plan document exists
- **WHEN** 本 change 完成
- **THEN** 仓库包含 `docs/archive/knowledge-bridge-migration-plan.md`

#### Scenario: Migration plan links from capability doc
- **WHEN** 读者查看 `docs/capabilities/knowledge-base.md`
- **THEN** 文档链接到 archived migration plan，并说明 knowledge-base 将按拆分 specs 渐进实现

### Requirement: Migration asset classification
迁移计划 SHALL 将 `knowledge-bridge` 资产分为可直接迁移、可参考但需重写、暂缓迁移和不迁移。

#### Scenario: Direct migration candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到可直接迁移的 parser、connector、sync 或 audit 候选能力

#### Scenario: Rewrite candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到需要重写的 vector store、embedding、chunking、retrieval 或 query scope 能力及原因

#### Scenario: Deferred and rejected candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到暂缓迁移和不迁移的能力及原因

### Requirement: Fleetent constraint mapping
迁移计划 SHALL 明确 `knowledge-bridge` 与 fleetent 约束之间的差异。

#### Scenario: Disallowed dependencies are documented
- **WHEN** 读者查看 migration plan
- **THEN** LlamaIndex、LanceDB direct dependency、OpenAI Embeddings default 和 standalone REST service boundary 的处理方式被明确说明

### Requirement: Knowledge-base spec split
迁移计划 SHALL 输出 fleetent knowledge-base 后续 specs 的拆分顺序、边界和依赖。

#### Scenario: Core spec is defined
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到 `knowledge-base-core` 的最小范围和不包含范围

#### Scenario: Follow-up specs are defined
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到 parser、connector、hybrid search、graph search 和 sync planner 后续 specs 的建议顺序

### Requirement: Knowledge-base runtime foundation
系统 SHALL 提供 `intelligence.knowledge_base` runtime package，用于手动导入文本内容、建立 chunk
索引并按 tenant + kb 隔离检索。

#### Scenario: Public API is importable
- **WHEN** 调用方导入 `KnowledgeDocument`、`KnowledgeChunk`、`ingest_text`、`search` 和 `delete`
- **THEN** 导入成功

#### Scenario: Knowledge-base config defaults
- **WHEN** 未显式配置 knowledge_base
- **THEN** `knowledge_base.enabled` 默认为 false
- **AND** `default_tenant_id` 默认为 `"default"`
- **AND** `default_kb_id` 默认为 `"global"`
- **AND** chunk size 和 overlap 有稳定默认值

#### Scenario: Knowledge-base owns schema
- **WHEN** Alembic upgrade 到 head
- **THEN** 数据库包含 knowledge-base-owned `knowledge_bases`、`knowledge_documents` 和 `knowledge_chunks`
- **AND** migration 标明 owner module 是 knowledge-base

### Requirement: Manual text ingest and chunk indexing
系统 SHALL 支持手动导入 text / markdown 内容，生成 deterministic chunks 并写入 vector_store。

#### Scenario: Ingest creates document and chunks
- **WHEN** 调用 `ingest_text(filename, content, tenant_id, kb_id, source, source_url)`
- **THEN** 系统创建 document record
- **AND** 系统按 deterministic chunking 创建有序 chunks

#### Scenario: Empty content is rejected
- **WHEN** 导入内容为空或全空白
- **THEN** 系统 fail fast

#### Scenario: Chunks are indexed in vector store
- **WHEN** ingest 创建 chunk
- **THEN** 系统调用 `vector_store.upsert(chunk_id, chunk_content, knowledge_namespace(tenant_id, kb_id))`

#### Scenario: Ingest is tenant and kb scoped
- **WHEN** 同一 filename 被导入不同 tenant 或 kb
- **THEN** records 与 vector namespace 相互隔离

### Requirement: Vector-only knowledge search
系统 SHALL 提供 vector-only `search(query, tenant_id, kb_ids, limit)`，返回相关 `KnowledgeChunk`。

#### Scenario: Search returns chunks with metadata
- **WHEN** query 命中已导入 chunks
- **THEN** 返回的 `KnowledgeChunk` 包含 chunk id、document id、filename、content、score、tenant_id 和 kb_id

#### Scenario: Search supports multiple knowledge bases
- **WHEN** `kb_ids` 包含多个 kb
- **THEN** 系统分别查询对应 namespace 并合并结果

#### Scenario: Search is tenant isolated
- **WHEN** tenant A 和 tenant B 有相似内容
- **THEN** tenant A 的 search 不返回 tenant B 的 chunks

#### Scenario: Search respects limit and stable ordering
- **WHEN** search 返回多条候选
- **THEN** 返回数量不超过 limit
- **AND** 结果按 score DESC、chunk position ASC、chunk id ASC 稳定排序

### Requirement: Knowledge document deletion
系统 SHALL 支持删除 document 及其 chunks 和 vector index entries。

#### Scenario: Delete removes document chunks
- **WHEN** 调用 `delete(document_id)`
- **THEN** document 和关联 chunks 不再被 search 返回

#### Scenario: Delete removes vector entries
- **WHEN** 删除 document
- **THEN** 系统为该 document 的每个 chunk 调用 `vector_store.delete(chunk_id, namespace)`

#### Scenario: Delete is idempotent
- **WHEN** 删除不存在或已删除的 document
- **THEN** 系统不报错

### Requirement: Basic parser public API
系统 SHALL 提供无 AI 框架依赖的基础 parser API，将 text、Markdown 和 lightweight HTML 转换为
structured parsed sections。

#### Scenario: Parser API is importable
- **WHEN** 调用方导入 `ParsedSection`、`ParsedDocument`、`parse_text`、`parse_markdown` 和 `parse_html`
- **THEN** 导入成功

#### Scenario: Parsed document shape
- **WHEN** parser 返回 `ParsedDocument`
- **THEN** 结果包含 filename、format、sections 和 metadata
- **AND** 每个 section 包含 title、text、level 和 metadata

### Requirement: Text parser
系统 SHALL 支持 plain text parser，用于无结构文本导入。

#### Scenario: Text body section
- **WHEN** 解析非空 text
- **THEN** parser 返回一个 body section

#### Scenario: Empty text rejected
- **WHEN** text 内容为空或全空白
- **THEN** parser fail fast

### Requirement: Markdown parser
系统 SHALL 支持基础 Markdown section parser。

#### Scenario: Markdown headings create sections
- **WHEN** Markdown 包含多级 heading
- **THEN** parser 按 heading 生成 sections
- **AND** section metadata 保留 heading path

#### Scenario: Fenced code blocks are preserved
- **WHEN** Markdown fenced code block 内包含 `#`
- **THEN** parser 不把 code block 内容误识别为 heading

#### Scenario: Empty sections are removed
- **WHEN** heading 下没有有效文本
- **THEN** parser 不输出空 section

### Requirement: Lightweight HTML parser
系统 SHALL 支持 lightweight HTML parser，用于后续 Confluence / HTML 文档适配。

#### Scenario: Unsafe or non-content elements are ignored
- **WHEN** HTML 包含 script 或 style
- **THEN** parser 输出不包含这些内容

#### Scenario: HTML headings and body text create sections
- **WHEN** HTML 包含 title、heading 和段落
- **THEN** parser 输出对应 sections

#### Scenario: Simple tables become searchable text
- **WHEN** HTML 包含简单 table
- **THEN** parser 将 table cells 转为可检索文本

### Requirement: Parsed ingest adapter
系统 SHALL 允许 core ingest 消费 parsed sections 并保留 section metadata。

#### Scenario: Parsed sections are ingested
- **WHEN** 调用 parsed ingest API
- **THEN** 系统为 parsed sections 生成 chunks 并写入 vector_store

#### Scenario: Chunk metadata includes section context
- **WHEN** parsed section 生成 chunk
- **THEN** chunk metadata 保留 section title 或 heading path

### Requirement: Parser dependency boundary
基础 parser SHALL 不引入 LlamaIndex、LangChain、docling、VLM 或外部解析服务依赖。高级 parser 可以引入
本地 PDF / Office 解析依赖，但不得引入 AI framework、OCR engine、VLM 或外部解析服务。

#### Scenario: No AI framework parser dependency
- **WHEN** parser changes 完成
- **THEN** runtime dependency 不包含 LlamaIndex、LangChain、docling 或 unstructured
- **AND** 不包含 OCR engine 或 VLM dependency

### Requirement: Knowledge-base search modes
系统 SHALL 支持 vector、keyword 和 hybrid 三种 knowledge-base search mode。

#### Scenario: Vector mode remains available
- **WHEN** 调用 `search(..., mode="vector")`
- **THEN** 系统使用 vector_store 检索 chunks

#### Scenario: Keyword mode is available
- **WHEN** 调用 `search(..., mode="keyword")`
- **THEN** 系统使用 SQLite FTS5 / BM25 检索 chunks

#### Scenario: Hybrid mode is available
- **WHEN** 调用 `search(..., mode="hybrid")`
- **THEN** 系统同时使用 vector 和 keyword candidates 并融合排序

#### Scenario: Unsupported search mode fails fast
- **WHEN** 调用方传入未知 mode
- **THEN** 系统 fail fast

### Requirement: Keyword indexing
系统 SHALL 为 knowledge chunks 维护 SQLite FTS5 keyword index。

#### Scenario: Ingest updates keyword index
- **WHEN** ingest 创建 chunk
- **THEN** chunk content 可被 keyword search 命中

#### Scenario: Delete removes keyword index entries
- **WHEN** document 被删除
- **THEN** 关联 chunks 不再被 keyword search 返回

#### Scenario: Keyword index is tenant and kb scoped
- **WHEN** 不同 tenant 或 kb 存在相同关键词
- **THEN** keyword search 只返回查询范围内的 chunks

### Requirement: Keyword retrieval behavior
系统 SHALL 支持适合企业文档的精确词检索。

#### Scenario: Exact identifiers are searchable
- **WHEN** chunk 包含产品编号、错误码或专有名词
- **THEN** keyword search 可以命中该 chunk

#### Scenario: Keyword search respects limit
- **WHEN** keyword search 找到多条结果
- **THEN** 返回数量不超过 limit

#### Scenario: Keyword search returns KnowledgeChunk
- **WHEN** keyword search 返回结果
- **THEN** result shape 仍为 `KnowledgeChunk`

### Requirement: Hybrid RRF fusion
系统 SHALL 使用 RRF 或等价稳定策略融合 vector 和 keyword candidates。

#### Scenario: Hybrid deduplicates chunks
- **WHEN** 同一 chunk 同时出现在 vector 和 keyword candidates
- **THEN** hybrid result 只包含一次该 chunk

#### Scenario: Hybrid boosts dual matches
- **WHEN** 一个 chunk 同时被 vector 和 keyword 命中
- **THEN** 该 chunk 排名优先于只被单侧弱命中的候选

#### Scenario: Hybrid degrades when one side is empty
- **WHEN** vector 或 keyword 单侧无结果
- **THEN** hybrid search 仍返回另一侧结果

#### Scenario: Hybrid search does not rerank by default
- **WHEN** 调用 `search(..., mode="hybrid")` 且未传入 `rerank=True`
- **THEN** 系统不调用 rerank provider
- **AND** 返回当前 hybrid fused ranking

### Requirement: Hybrid search excludes advanced retrieval
knowledge-base search SHALL NOT implement rerank provider, query planner, graph search or external search
backend as part of default vector、keyword 或 hybrid search。

#### Scenario: Hybrid search does not rerank by default
- **WHEN** 调用 `search(..., mode="hybrid")` 且未传入 `rerank=True`
- **THEN** 系统不调用 rerank provider
- **AND** 返回当前 hybrid fused ranking

#### Scenario: Graph search remains separate
- **WHEN** 调用 `search(...)`
- **THEN** 系统不执行 graph search relation expansion

#### Scenario: Query planner remains separate
- **WHEN** 调用 `search(...)`
- **THEN** 系统不执行 planner-driven multi-step retrieval

### Requirement: Knowledge-base connector boundary
系统 SHALL 提供 DataSource / DocumentRef 边界，供不同文档来源接入 knowledge-base ingest。

#### Scenario: Connector API is importable
- **WHEN** 调用方导入 `DocumentRef` 和 `DataSource`
- **THEN** 导入成功

#### Scenario: DocumentRef shape
- **WHEN** connector 返回 `DocumentRef`
- **THEN** ref 包含 id、filename、format、path 或 url、metadata

### Requirement: Local directory data source
系统 SHALL 支持从显式允许的本地目录列举和读取文档。

#### Scenario: Local source only scans allowlisted root
- **WHEN** 配置 local directory source
- **THEN** connector 只读取该 root 下文件

#### Scenario: Path traversal is rejected
- **WHEN** 请求读取 allowlisted root 外的路径
- **THEN** 系统 fail fast

#### Scenario: Supported local formats
- **WHEN** local directory 包含 `.txt`、`.md`、`.html` 或 `.htm`
- **THEN** connector 返回对应 `DocumentRef`

#### Scenario: Unsupported local formats are skipped
- **WHEN** local directory 包含不支持后缀
- **THEN** connector 跳过该文件并在 sync summary 中体现

### Requirement: Local manual sync
系统 SHALL 提供手动 local directory sync，将支持的文件解析并导入指定 tenant/kb。

#### Scenario: Manual sync ingests supported files
- **WHEN** 调用 local sync API
- **THEN** 系统读取支持文件，调用 parser，并通过 core ingest 写入 KB

#### Scenario: Manual sync is tenant and kb scoped
- **WHEN** 同一目录同步到不同 tenant/kb
- **THEN** 文档和 chunks 写入对应 KB scope

#### Scenario: Manual sync returns summary
- **WHEN** local sync 完成
- **THEN** 返回 scanned、ingested、skipped、failed 等摘要计数

### Requirement: Local source state
系统 SHALL 记录本地文件状态，避免未变化文件重复 ingest。

#### Scenario: Unchanged files are skipped
- **WHEN** 文件 path、mtime 和 content hash 均未变化
- **THEN** 下一次 sync 不重复 ingest

#### Scenario: Changed files are reingested
- **WHEN** 文件内容 hash 变化
- **THEN** 下一次 sync 重新 ingest 该文件

### Requirement: Local connector excludes advanced sync
local connector SHALL NOT implement scheduler, Confluence, Google Drive, ACL enforcement or multi-worker
runtime.

#### Scenario: No scheduler dependency
- **WHEN** local sync 完成
- **THEN** 没有新增后台 scheduler 或 worker 进程要求

### Requirement: Knowledge-base retrieval evaluation fixtures
系统 SHALL 提供 deterministic retrieval evaluation fixtures，用于验证 KB ingest/chunking/search 质量基线。

#### Scenario: Fixture schema is explicit
- **WHEN** evaluation runner 加载 fixture
- **THEN** fixture 包含 name、documents、queries、expected_chunks 和 forbidden_chunks

#### Scenario: Invalid fixture is rejected
- **WHEN** fixture 缺失必需字段
- **THEN** evaluation runner 报告 fixture validation failure

### Requirement: Deterministic retrieval evaluation
系统 SHALL 默认使用 deterministic embedding 和 isolated storage 运行 KB retrieval evaluation。

#### Scenario: Runner ingests documents
- **WHEN** evaluation case 运行
- **THEN** runner 将 fixture documents 导入 tmp knowledge-base store

#### Scenario: Expected chunks are validated
- **WHEN** query 运行完成
- **THEN** runner 验证 expected chunks 或 snippets 出现在 top-k 结果中

#### Scenario: Forbidden chunks are rejected
- **WHEN** query 运行完成
- **THEN** runner 验证 forbidden chunks 或 snippets 不出现在结果中

#### Scenario: Evaluation isolates storage
- **WHEN** evaluation case 运行
- **THEN** SQLite 使用 tmp path
- **AND** 不触碰 `data/`

### Requirement: Optional real embedding retrieval evaluation
系统 SHALL 提供显式启用的真实 embedding retrieval evaluation，默认跳过。

#### Scenario: Real embedding evaluation is skipped by default
- **WHEN** 未设置 `FLEETENT_EVAL_REAL_EMBEDDING=1`
- **THEN** real embedding evaluation case 被 skip

#### Scenario: Real embedding evaluation requires provider credentials
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 但缺少 provider credentials
- **THEN** real embedding evaluation case 被 skip

#### Scenario: Real embedding evaluation is manually runnable
- **WHEN** 设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 且 provider 配置完整
- **THEN** runner 可以使用真实 HTTP embedding provider 运行 fixture

### Requirement: Knowledge-base sync planner public API
系统 SHALL 提供 knowledge-base sync planner public API，用于在执行 source sync 前生成确定性的同步计划。

#### Scenario: Sync planner API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `SyncAction`、`SyncPlan`、`SyncPlanItem`、sync summary dataclasses、`plan_local_directory_sync` 和 `execute_sync_plan`
- **THEN** 导入成功

#### Scenario: Empty source plan
- **WHEN** local source 目录没有支持或不支持的文件，且没有历史 source state
- **THEN** planner 返回空 plan items
- **AND** summary 中 scanned、planned、unsupported 均为 0

### Requirement: Sync plan separates planning from execution
sync planner SHALL 在写入 KB documents、chunks、vector index 或 source state 前产出计划。

#### Scenario: Planning does not mutate knowledge base
- **WHEN** 调用 `plan_local_directory_sync()`
- **THEN** 系统可以列举、读取和 hash source documents
- **AND** 不调用 `ingest_parsed()`、`delete()` 或 vector_store mutation
- **AND** 不写入 `knowledge_source_states`

#### Scenario: Execution applies a plan
- **WHEN** 调用 `execute_sync_plan()`
- **THEN** 系统只按 plan items 执行 ingest、reingest、delete 或 skip

### Requirement: Local sync action planning
系统 SHALL 为 local directory source documents 生成 new、changed、unchanged 和 unsupported actions。

#### Scenario: New file is planned for ingest
- **WHEN** local source 包含支持格式文件，且 `knowledge_source_states` 中没有该 source path
- **THEN** planner 为该文件生成 `ingest_new` plan item

#### Scenario: Changed file is planned for reingest
- **WHEN** local source 文件的 mtime 或 content hash 与 source state 不一致
- **THEN** planner 为该文件生成 `reingest_changed` plan item

#### Scenario: Unchanged file is planned for skip
- **WHEN** local source 文件的 path、mtime 和 content hash 均与 source state 一致
- **THEN** planner 为该文件生成 `skip_unchanged` plan item

#### Scenario: Unsupported files are counted
- **WHEN** local source 包含不支持后缀
- **THEN** planner summary 记录 unsupported 数量
- **AND** unsupported 文件不会生成 ingest 或 reingest item

### Requirement: Missing-source delete planning
系统 SHALL 检测之前同步过但当前 source listing 中缺失的 local source path，并计划删除对应 KB document。

#### Scenario: Missing source file is planned for delete
- **WHEN** `knowledge_source_states` 中存在某 source path
- **AND** 当前 local source listing 不再包含该 path
- **THEN** planner 生成 `delete_missing` plan item

#### Scenario: Delete plan item includes target document
- **WHEN** planner 生成 `delete_missing` item
- **THEN** item 包含 source_id、tenant_id、kb_id、source_path 和 document_id

### Requirement: Sync plan execution
系统 SHALL 幂等执行 sync plan items，并在单个 item 失败时继续处理其他 items。

#### Scenario: Execute ingest new
- **WHEN** executor 处理 `ingest_new` item
- **THEN** 系统解析 source content，调用 `ingest_parsed()`
- **AND** ingest 成功后写入 `knowledge_source_states`

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 `reingest_changed` item
- **THEN** 系统删除旧 document
- **AND** 解析并 ingest 新 document
- **AND** 成功后更新 `knowledge_source_states`

#### Scenario: Execute delete missing
- **WHEN** executor 处理 `delete_missing` item
- **THEN** 系统调用 `delete(document_id)`
- **AND** 删除对应 `knowledge_source_states` 记录

#### Scenario: Execute skip unchanged
- **WHEN** executor 处理 `skip_unchanged` item
- **THEN** 系统不调用 parser、`ingest_parsed()` 或 `delete()`
- **AND** summary 记录 unchanged / skipped

#### Scenario: Per item failure isolation
- **WHEN** 某个 plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 plan items

### Requirement: Local sync delegates to planner
`sync_local_directory()` SHALL 通过 sync planner 和 executor 完成同步，而不是直接边扫描边写入 KB。

#### Scenario: Local sync summary matches plan execution
- **WHEN** 调用 `sync_local_directory()`
- **THEN** 返回 summary 反映 planner 和 executor 的 scanned、ingested、skipped、failed、unsupported、unchanged 和 deleted 计数

#### Scenario: Repeated sync remains idempotent
- **WHEN** 对同一 local source 连续调用两次 `sync_local_directory()`
- **THEN** 第二次 sync 对未变化文件返回 unchanged / skipped
- **AND** 不重复创建 KB documents 或 chunks

#### Scenario: Removed local file is deleted from KB
- **WHEN** 某文件已同步到 KB
- **AND** 该文件随后从 local source 删除
- **AND** 再次调用 `sync_local_directory()`
- **THEN** 对应 KB document 被删除
- **AND** search 不再返回该 document 的 chunks

### Requirement: Sync planner excludes advanced connector runtime
sync planner SHALL NOT introduce scheduler、background worker、remote connector、sync run persistence 或 connector-specific credential lifecycle。

#### Scenario: No scheduler or worker dependency
- **WHEN** sync planner change 完成
- **THEN** 系统不要求新增 scheduler、queue、worker 或动态 job runtime

#### Scenario: No remote connector behavior
- **WHEN** sync planner change 完成
- **THEN** 系统不包含 Confluence、Google Drive 或其他 remote connector 实现

### Requirement: Knowledge-base indexable iterator
knowledge-base SHALL 提供 public API，用于枚举指定 tenant/kb 当前应写入 vector_store 的 chunk source records。

#### Scenario: Knowledge-base indexable API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `iter_indexable_knowledge_chunks`
- **THEN** 导入成功

#### Scenario: Knowledge-base indexable items are tenant and kb scoped
- **WHEN** 多个 tenant 或 kb 都有 chunks
- **AND** 调用 `iter_indexable_knowledge_chunks(tenant_id, kb_id)`
- **THEN** 返回结果只包含该 tenant/kb 的 chunks

#### Scenario: Knowledge-base indexable item namespace
- **WHEN** `iter_indexable_knowledge_chunks()` 返回 item
- **THEN** item.namespace 等于 `knowledge_namespace(tenant_id, kb_id)`
- **AND** item.id 等于 chunk id
- **AND** item.content 等于 chunk content

### Requirement: Knowledge-base indexable iterator is a public boundary
vector_store reindex SHALL consume knowledge-base indexable records through knowledge-base public API, not direct SQL.

#### Scenario: Reindex does not query knowledge tables directly
- **WHEN** knowledge-base reindex 执行
- **THEN** reindex code 调用 `knowledge_base.iter_indexable_knowledge_chunks()`
- **AND** 不直接访问 `knowledge_documents`、`knowledge_chunks` 或 `knowledge_chunks_fts` 表

### Requirement: Knowledge-base combined embedding evaluation
系统 SHALL 在 combined embedding evaluation 中覆盖 knowledge-base retrieval，验证 KB search 经由
vector-store embedding / reindex 路径后的召回行为。

#### Scenario: Knowledge-base retrieval fixture is explicit
- **WHEN** evaluation runner 加载 combined embedding fixture
- **THEN** fixture 包含 KB documents、KB queries、expected KB snippets 和 forbidden KB snippets

#### Scenario: Knowledge-base index is rebuilt through public reindex
- **WHEN** deterministic combined embedding evaluation 运行
- **THEN** runner 调用 `vector_store.reindex(ReindexRequest(owner="knowledge_base", tenant_id=..., kb_id=...))`

#### Scenario: Expected KB snippets are retrieved
- **WHEN** KB query 运行完成
- **THEN** runner 验证 expected KB snippets 出现在 `knowledge_base.search()` top-k 结果中

#### Scenario: Forbidden KB snippets are rejected
- **WHEN** KB query 运行完成
- **THEN** runner 验证 forbidden KB snippets 不出现在 `knowledge_base.search()` top-k 结果中

### Requirement: Google Drive connector configuration
knowledge-base SHALL provide Google Drive connector configuration scoped to a target tenant and knowledge base.

#### Scenario: Google Drive connector config is importable
- **WHEN** 调用方从 knowledge-base public API 导入 Google Drive connector config
- **THEN** 导入成功

#### Scenario: Connector is scoped to tenant kb and folder
- **WHEN** 配置 Google Drive connector
- **THEN** config 包含 connector_id、tenant_id、kb_id、folder_id 和 OAuth credential_ref
- **AND** connector 只同步到指定 tenant_id + kb_id

#### Scenario: Connector uses OAuth user authorization
- **WHEN** connector 访问 Google Drive
- **THEN** 使用绑定到 connector 的 OAuth 用户授权
- **AND** 不要求 service account 或 domain-wide delegation

#### Scenario: OAuth credential belongs to connector
- **WHEN** 用户查询已同步 KB
- **THEN** 系统不使用该聊天用户的 Google Drive token 做实时过滤
- **AND** 已同步内容的访问控制由 KB scope 和后续 agent-KB binding 决定

#### Scenario: File based credential ref is supported
- **WHEN** Google Drive connector config 使用 file-based credential_ref
- **THEN** 系统可以从该引用加载 OAuth token
- **AND** 不要求新增 credential 表

### Requirement: Google Drive folder listing
Google Drive connector SHALL list documents from a configured folder scope instead of scanning the entire Drive.

#### Scenario: Folder scoped listing
- **WHEN** connector 运行 sync plan
- **THEN** 它只列举配置的 folder_id 范围内文档

#### Scenario: Unsupported MIME types are skipped
- **WHEN** folder 中包含 unsupported MIME type
- **THEN** planner 或 executor 跳过该文件
- **AND** summary 记录 unsupported 数量

#### Scenario: Auth failure is recorded
- **WHEN** OAuth token refresh 失败或 Drive API 返回授权失败
- **THEN** connector 标记为 `auth_failed`
- **AND** 不写入 KB documents、chunks 或 vector index

### Requirement: Google Drive content parsing
Google Drive connector SHALL map supported Drive content into knowledge-base parser registry.

#### Scenario: Google Docs export uses HTML parser
- **WHEN** connector 同步 Google Docs
- **THEN** 它通过 Drive export API 导出 HTML
- **AND** 调用 HTML parser 生成 parsed document

#### Scenario: Plain text uses text parser
- **WHEN** connector 同步 plain text 文件
- **THEN** 它调用 text parser

#### Scenario: Markdown uses markdown parser
- **WHEN** connector 同步 Markdown 文件
- **THEN** 它调用 Markdown parser

#### Scenario: HTML file uses HTML parser
- **WHEN** connector 同步 HTML 文件
- **THEN** 它调用 HTML parser

#### Scenario: Google Sheets and Slides are exported to supported Office formats
- **WHEN** connector 遇到 Google Sheets 或 Google Slides
- **THEN** Google Sheets 导出为 `.xlsx`
- **AND** Google Slides 导出为 `.pptx`
- **AND** 导出内容通过 parser registry 解析

### Requirement: Google Drive sync planning
knowledge-base SHALL plan Google Drive sync actions before mutating KB documents, chunks, vector index, or source state.

#### Scenario: New Drive file is planned for ingest
- **WHEN** Drive folder 包含 supported file
- **AND** source state 中没有该 remote file
- **THEN** planner 生成 `ingest_new` item

#### Scenario: Changed Drive file is planned for reingest
- **WHEN** remote file modified time、revision 或 content hash 与 source state 不一致
- **THEN** planner 生成 `reingest_changed` item

#### Scenario: Unchanged Drive file is skipped
- **WHEN** remote file metadata 与 source state 一致
- **THEN** planner 生成 `skip_unchanged` item

#### Scenario: Missing Drive file is archived
- **WHEN** source state 中存在 remote file
- **AND** 当前 folder listing 不再包含该 file 或授权账号不再可见
- **THEN** planner 生成 `archive_missing` item
- **AND** 不生成 physical delete item

### Requirement: Google Drive sync execution
knowledge-base SHALL execute Google Drive sync plans through existing parser and KB public APIs.

#### Scenario: Execute ingest new
- **WHEN** executor 处理 Google Drive `ingest_new` item
- **THEN** 系统读取或 export 文件内容
- **AND** 调用 parser
- **AND** 调用 `ingest_parsed()` 写入指定 tenant_id + kb_id
- **AND** 成功后更新 source state

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 Google Drive `reingest_changed` item
- **THEN** 系统更新对应 KB document / chunks
- **AND** 成功后更新 source state

#### Scenario: Execute archive missing
- **WHEN** executor 处理 `archive_missing` item
- **THEN** 系统标记对应 source / document 为 archived 或 missing
- **AND** 不调用 physical `delete(document_id)`
- **AND** 默认 search 不返回 archived document 的 chunks

#### Scenario: Per item failure isolation
- **WHEN** 某个 Google Drive plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 item

### Requirement: Google Drive manual sync public API
knowledge-base SHALL expose manual Google Drive sync APIs that delegate to planner and executor.

#### Scenario: Google Drive sync API is importable
- **WHEN** 调用方从 knowledge-base public API 导入 `plan_google_drive_sync` 和 `sync_google_drive`
- **THEN** 导入成功

#### Scenario: Manual sync delegates to planner
- **WHEN** 调用 `sync_google_drive()`
- **THEN** 系统先生成 sync plan
- **AND** 再执行 plan
- **AND** 不边扫描边直接写 KB

#### Scenario: Manual sync returns summary
- **WHEN** Google Drive sync 完成
- **THEN** summary 包含 scanned、planned、ingested、changed、unchanged、unsupported、archived、failed 和 auth_failed 计数或状态

### Requirement: Google Drive connector tests avoid real API by default
Google Drive connector tests SHALL use fake clients by default and SHALL NOT connect to real Google APIs unless explicitly enabled.

#### Scenario: Default tests use fake Drive client
- **WHEN** 默认测试运行
- **THEN** 测试使用 fake Drive client / fixtures
- **AND** 不访问真实 Google API

#### Scenario: Real smoke requires explicit opt-in
- **WHEN** 未设置 `FLEETENT_GOOGLE_DRIVE_SMOKE=1`
- **THEN** Google Drive real smoke test 被 skip

#### Scenario: Real smoke skips without credentials
- **WHEN** 设置 `FLEETENT_GOOGLE_DRIVE_SMOKE=1` 但缺少 OAuth credential_ref 或 folder id
- **THEN** real smoke test 被 skip

### Requirement: Confluence connector configuration
knowledge-base SHALL provide Confluence connector configuration scoped to a target tenant and knowledge base.

#### Scenario: Confluence connector config is importable
- **WHEN** 调用方从 knowledge-base public API 导入 Confluence connector config
- **THEN** 导入成功

#### Scenario: Connector is scoped to tenant kb and Confluence scope
- **WHEN** 配置 Confluence connector
- **THEN** config 包含 connector_id、tenant_id、kb_id、base_url、username 和 API token credential_ref
- **AND** config 包含 space scope、page scope 或 page include_children scope
- **AND** connector 只同步到指定 tenant_id + kb_id

#### Scenario: Connector uses Confluence Cloud API token
- **WHEN** connector 访问 Confluence
- **THEN** 使用绑定到 connector 的 Confluence Cloud username + API token credential
- **AND** 不要求 Server / Data Center、Basic Auth 或 PAT 分支

#### Scenario: Confluence credential belongs to connector
- **WHEN** 用户查询已同步 KB
- **THEN** 系统不使用该聊天用户的 Confluence credential 做实时过滤
- **AND** 已同步内容的访问控制由 KB scope 和后续 agent-KB binding 决定

### Requirement: Confluence scope listing
Confluence connector SHALL list pages from configured scopes instead of scanning the entire site.

#### Scenario: Space scope lists pages
- **WHEN** connector 配置 space_key
- **THEN** planner 只列举该 space 中 pages

#### Scenario: Page scope lists one page
- **WHEN** connector 配置 page_id 且 include_children=false
- **THEN** planner 只列举该 page

#### Scenario: Page children scope lists descendants
- **WHEN** connector 配置 page_id 且 include_children=true
- **THEN** planner 列举该 page 及 descendant pages

#### Scenario: Auth failure is recorded
- **WHEN** API token 无效、权限不足或 Confluence API 返回授权失败
- **THEN** connector 标记为 `auth_failed`
- **AND** 不写入 KB documents、chunks 或 vector index

### Requirement: Confluence page parsing
Confluence connector SHALL fetch page storage HTML and map it into existing knowledge-base parsers.

#### Scenario: Page fetch expands required fields
- **WHEN** connector 拉取 Confluence page
- **THEN** 请求包含 storage HTML、version、space 和 ancestors 信息

#### Scenario: Storage HTML uses HTML parser
- **WHEN** connector 同步 Confluence page
- **THEN** 它调用现有 HTML parser 生成 parsed document

#### Scenario: Page metadata is preserved
- **WHEN** connector 同步 Confluence page
- **THEN** parsed metadata 包含 page id、title、space key、ancestors 或 path text

### Requirement: Confluence sync planning
knowledge-base SHALL plan Confluence sync actions before mutating KB documents, chunks, vector index, or source state.

#### Scenario: New page is planned for ingest
- **WHEN** Confluence scope 包含 page
- **AND** source state 中没有该 page
- **THEN** planner 生成 `ingest_new` item

#### Scenario: Changed page is planned for reingest
- **WHEN** page version 或 modified time 与 source state 不一致
- **THEN** planner 生成 `reingest_changed` item

#### Scenario: Unchanged page is skipped
- **WHEN** page metadata 与 source state 一致
- **THEN** planner 生成 `skip_unchanged` item

#### Scenario: Missing page is archived
- **WHEN** source state 中存在 page
- **AND** 当前 scope listing 不再包含该 page 或 credential 不再可见
- **THEN** planner 生成 `archive_missing` item
- **AND** 不生成 physical delete item

### Requirement: Confluence sync execution
knowledge-base SHALL execute Confluence sync plans through existing parser and KB public APIs.

#### Scenario: Execute ingest new
- **WHEN** executor 处理 Confluence `ingest_new` item
- **THEN** 系统读取 page storage HTML
- **AND** 调用 HTML parser
- **AND** 调用 `ingest_parsed()` 写入指定 tenant_id + kb_id
- **AND** 成功后更新 source state

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 Confluence `reingest_changed` item
- **THEN** 系统更新对应 KB document / chunks
- **AND** 成功后更新 source state

#### Scenario: Execute archive missing
- **WHEN** executor 处理 `archive_missing` item
- **THEN** 系统标记对应 source / document 为 archived 或 missing
- **AND** 不调用 physical `delete(document_id)`
- **AND** 默认 search 不返回 archived document 的 chunks

#### Scenario: Per item failure isolation
- **WHEN** 某个 Confluence plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 item

### Requirement: Confluence rate limit and retry
Confluence connector SHALL tolerate basic rate limiting without failing the entire sync.

#### Scenario: Retry after rate limit
- **WHEN** Confluence API 返回 429 和 Retry-After
- **THEN** connector 等待 Retry-After 后重试该请求

#### Scenario: Retry exhaustion records failure
- **WHEN** 请求超过重试上限
- **THEN** 当前 item 记录 failed
- **AND** 后续 item 继续执行

### Requirement: Confluence manual sync public API
knowledge-base SHALL expose manual Confluence sync APIs that delegate to planner and executor.

#### Scenario: Confluence sync API is importable
- **WHEN** 调用方从 knowledge-base public API 导入 `plan_confluence_sync` 和 `sync_confluence`
- **THEN** 导入成功

#### Scenario: Manual sync delegates to planner
- **WHEN** 调用 `sync_confluence()`
- **THEN** 系统先生成 sync plan
- **AND** 再执行 plan
- **AND** 不边扫描边直接写 KB

#### Scenario: Manual sync returns summary
- **WHEN** Confluence sync 完成
- **THEN** summary 包含 scanned、planned、ingested、changed、unchanged、archived、failed 和 auth_failed 计数或状态

### Requirement: Confluence connector tests avoid real API by default
Confluence connector tests SHALL use fake clients by default and SHALL NOT connect to real Confluence unless explicitly enabled.

#### Scenario: Default tests use fake Confluence client
- **WHEN** 默认测试运行
- **THEN** 测试使用 fake Confluence client / fixtures
- **AND** 不访问真实 Confluence

#### Scenario: Real smoke requires explicit opt-in
- **WHEN** 未设置 `FLEETENT_CONFLUENCE_SMOKE=1`
- **THEN** Confluence real smoke test 被 skip

#### Scenario: Real smoke skips without credentials
- **WHEN** 设置 `FLEETENT_CONFLUENCE_SMOKE=1` 但缺少 base URL、username、credential_ref 或 scope
- **THEN** real smoke test 被 skip

### Requirement: Agent knowledge-base binding public API
系统 SHALL 提供 agent 到 knowledge base 的绑定 public API，用于声明某个 tenant 下的 agent 可以检索哪些 KB。

#### Scenario: Binding API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `AgentKnowledgeBaseBinding`、
  `bind_agent_to_kb`、`unbind_agent_from_kb`、`list_agent_kb_bindings` 和 `resolve_agent_kb_ids`
- **THEN** 导入成功

#### Scenario: Binding table exists
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 knowledge-base-owned `knowledge_base_agent_bindings` 表
- **AND** 表对 `tenant_id + agent_id + kb_id` 施加唯一约束

### Requirement: Agent KB binding behavior
系统 SHALL 支持按 tenant 和 agent 管理显式 KB 绑定，且绑定行为保持幂等和隔离。

#### Scenario: Bind is idempotent
- **WHEN** 对同一 `tenant_id`、`agent_id` 和 `kb_id` 重复调用 `bind_agent_to_kb()`
- **THEN** 系统只保留一条绑定
- **AND** 调用不会因重复绑定失败

#### Scenario: Unbind is idempotent
- **WHEN** 对不存在的绑定调用 `unbind_agent_from_kb()`
- **THEN** 系统不报错

#### Scenario: Binding is tenant isolated
- **WHEN** 不同 tenant 中存在同名 agent 的 KB 绑定
- **THEN** 查询其中一个 tenant 的绑定不会返回另一个 tenant 的 KB

#### Scenario: Binding is agent isolated
- **WHEN** 同一 tenant 中不同 agent 绑定到不同 KB
- **THEN** 查询其中一个 agent 的绑定不会返回另一个 agent 的 KB

#### Scenario: Empty binding identifiers are rejected
- **WHEN** `tenant_id`、`agent_id` 或 `kb_id` 为空
- **THEN** 系统 fail fast

#### Scenario: Binding may reference future KB
- **WHEN** 调用 `bind_agent_to_kb()` 绑定当前尚不存在或尚无内容的 `kb_id`
- **THEN** 系统允许保存绑定

### Requirement: Agent KB scope resolution
系统 SHALL 提供 `resolve_agent_kb_ids(tenant_id, agent_id)` 作为 agent 有效 KB 范围的唯一解析入口。

#### Scenario: Explicit bindings override default KB
- **WHEN** agent 存在一个或多个显式 KB 绑定
- **THEN** `resolve_agent_kb_ids()` 返回显式绑定的 KB 列表
- **AND** 不额外返回默认 KB

#### Scenario: Missing binding falls back to default KB
- **WHEN** agent 没有显式 KB 绑定
- **AND** `Settings.knowledge_base.default_kb_id` 已配置
- **THEN** `resolve_agent_kb_ids()` 返回只包含默认 KB 的列表

#### Scenario: Missing default KB returns empty scope
- **WHEN** agent 没有显式 KB 绑定
- **AND** 默认 KB 未配置、为空或不可用
- **THEN** `resolve_agent_kb_ids()` 返回空列表
- **AND** 系统记录可诊断事件
- **AND** 系统不抛出阻断 agent 对话的业务错误

#### Scenario: Search with future or empty KB returns no chunks
- **WHEN** 调用 `knowledge_base.search()` 并传入不存在或暂无内容的 `kb_id`
- **THEN** 系统返回空结果
- **AND** 不把该情况视为绑定错误

### Requirement: Connector configuration registry
系统 SHALL 从非 secret 应用配置中加载 knowledge-base connector 定义，并以 `connector_id` 提供稳定查找入口。

#### Scenario: Google Drive connectors load from Platform Knowledge config
- **WHEN** Platform Knowledge config contains Google Drive connector definitions
- **THEN** 系统可以把每条配置解析为 Google Drive connector config

#### Scenario: Confluence connectors load from Platform Knowledge config
- **WHEN** Platform Knowledge config contains Confluence connector definitions
- **THEN** 系统可以把每条配置解析为 Confluence connector config

#### Scenario: Connector ids are globally unique
- **WHEN** 两个 connector 使用相同 `connector_id`
- **THEN** registry fail fast

#### Scenario: Disabled connectors are listed but not synced
- **WHEN** connector 配置 `enabled=false`
- **THEN** list 操作仍显示该 connector
- **AND** sync 操作返回 disabled 状态且不访问 remote API

### Requirement: Connector operations public API
系统 SHALL 提供 knowledge-base connector operations public API，用于列出、检查、同步和查看最近一次状态。

#### Scenario: Connector operations API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 connector operations dataclasses 和 functions
- **THEN** 导入成功

#### Scenario: List connectors returns safe summaries
- **WHEN** 调用 connector list operation
- **THEN** 返回 connector_id、type、enabled、tenant_id、kb_id 和 scope 摘要
- **AND** 不返回真实 credential payload

#### Scenario: Unknown connector fails clearly
- **WHEN** 对不存在的 `connector_id` 调用 check、sync 或 status operation
- **THEN** 系统返回明确的 not-found 错误

### Requirement: Connector credential and scope check
系统 SHALL 支持对 connector 的 `credential_ref` 和 remote scope 执行显式检查。

#### Scenario: Missing credential is reported
- **WHEN** `credential_ref` 指向不存在的文件或未设置的环境变量
- **THEN** check operation 返回 `credential_missing`

#### Scenario: Invalid credential is reported
- **WHEN** `credential_ref` 可读取但格式非法
- **THEN** check operation 返回 `credential_invalid`

#### Scenario: Auth failure is reported
- **WHEN** connector client 认证失败
- **THEN** check operation 返回 `auth_failed`

#### Scenario: Scope unreachable is reported
- **WHEN** connector client 无法访问配置的 folder、space 或 page scope
- **THEN** check operation 返回 `scope_unreachable`

#### Scenario: Check result is sanitized
- **WHEN** check operation 返回失败详情
- **THEN** 结果不包含 token、secret、credential payload 或完整文档正文

### Requirement: Connector sync dry-run
系统 SHALL 支持 connector sync dry-run，用于生成同步计划而不修改 KB 数据。

#### Scenario: Dry-run does not mutate knowledge data
- **WHEN** 调用 connector sync dry-run
- **THEN** 系统生成 plan summary
- **AND** 不写入 `knowledge_documents`
- **AND** 不写入 `knowledge_source_states`
- **AND** 不写入 vector_store

#### Scenario: Dry-run records dry-run status
- **WHEN** connector sync dry-run 完成
- **THEN** 系统更新该 connector 的最近一次状态为 dry-run 结果
- **AND** 状态不会被标记为真实 sync 成功

### Requirement: Connector sync operation
系统 SHALL 支持通过 connector operations 执行手动同步，并保存最近一次同步摘要。

#### Scenario: Sync runs matching connector executor
- **WHEN** 调用 connector sync operation
- **THEN** 系统根据 connector type 调用对应 Google Drive 或 Confluence sync executor

#### Scenario: Sync status summary is persisted
- **WHEN** connector sync 完成
- **THEN** 系统保存 scanned、planned、ingested、changed、unchanged、unsupported、archived、failed 和 auth_failed 计数

#### Scenario: Sync failure still records status
- **WHEN** connector sync 失败
- **THEN** 系统保存失败状态和脱敏错误摘要
- **AND** 后续 status 查询可返回该失败状态

### Requirement: Connector status persistence
系统 SHALL 保存每个 connector 最近一次运行状态，不保存完整运行历史。

#### Scenario: Status table exists
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 knowledge-base-owned `knowledge_connector_status` 表

#### Scenario: Only latest status is kept
- **WHEN** 同一 connector 多次写入 status
- **THEN** status 查询只返回最近一次结果

#### Scenario: Never-run status is stable
- **WHEN** connector 存在但从未执行 check、dry-run 或 sync
- **THEN** status operation 返回 `never_run`

#### Scenario: Status payload is sanitized
- **WHEN** status 包含 summary 或 error
- **THEN** 持久化内容不包含 token、secret、credential payload 或完整文档正文

### Requirement: Admin CLI connector operations
系统 SHALL 在 `fleetent-admin` 中提供 knowledge-base connector operations 命令。

#### Scenario: List connectors from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors list`
- **THEN** CLI 输出配置的 connector 摘要

#### Scenario: Check connector from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors check <connector_id>`
- **THEN** CLI 输出该 connector 的检查状态

#### Scenario: Show connector status from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors status <connector_id>`
- **THEN** CLI 输出该 connector 最近一次状态或 `never_run`

#### Scenario: Dry-run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id> --dry-run`
- **THEN** CLI 执行 dry-run 并输出 plan summary

#### Scenario: Run sync from CLI
- **WHEN** operator 运行 `fleetent-admin kb connectors sync <connector_id>`
- **THEN** CLI 执行真实 sync 并输出 sync summary

#### Scenario: CLI output is sanitized
- **WHEN** CLI 输出 connector check、sync 或 status 结果
- **THEN** 输出不包含 token、secret、credential payload 或完整文档正文

### Requirement: Advanced parser public API
knowledge-base SHALL provide local parsers for text-based PDF, DOCX, PPTX and XLSX documents without using AI frameworks or external parsing services.

#### Scenario: Advanced parser API is importable
- **WHEN** 调用方导入 `parse_pdf`、`parse_docx`、`parse_pptx`、`parse_xlsx` 和 `parse_document`
- **THEN** 导入成功

#### Scenario: Advanced parser dependencies are local only
- **WHEN** 查看 runtime dependencies
- **THEN** 可以使用 `pypdf`、`python-docx`、`python-pptx` 和 `openpyxl`
- **AND** 不包含 LlamaIndex、LangChain、docling、unstructured、OCR engine 或 VLM dependency

### Requirement: Parser registry dispatch
knowledge-base SHALL provide a parser registry that maps supported file extensions and MIME types to the correct parser.

#### Scenario: Registry dispatches basic formats
- **WHEN** 调用 `parse_document` 解析 `.txt`、`.md`、`.html` 或 `.htm`
- **THEN** registry 分别调用 text、Markdown 或 HTML parser

#### Scenario: Registry dispatches advanced formats
- **WHEN** 调用 `parse_document` 解析 `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** registry 分别调用 PDF、DOCX、PPTX 或 XLSX parser

#### Scenario: Registry dispatches by MIME type
- **WHEN** filename 缺少可识别 extension
- **AND** MIME type 是 supported type
- **THEN** registry 使用 MIME type 选择 parser

#### Scenario: Unsupported media type fails fast
- **WHEN** registry 收到 unsupported extension 和 MIME type
- **THEN** registry fail fast
- **AND** 错误信息不包含文件正文

### Requirement: Text-based PDF parser
knowledge-base SHALL parse text-based PDF files into sections with page metadata.

#### Scenario: PDF pages become sections
- **WHEN** parser 解析包含可抽取文本的 PDF
- **THEN** 每个有文本的 page 生成一个 section
- **AND** section metadata 包含 `page_number`

#### Scenario: Empty PDF extraction fails safely
- **WHEN** parser 解析扫描版或没有可抽取文本的 PDF
- **THEN** parser fail fast 或返回统一 empty-content failure
- **AND** 错误信息不包含文件正文

#### Scenario: Encrypted PDF fails safely
- **WHEN** parser 解析加密 PDF
- **THEN** parser fail fast
- **AND** 错误摘要说明 encrypted / unsupported
- **AND** 不输出文件正文

### Requirement: DOCX parser
knowledge-base SHALL parse DOCX paragraph and table text into searchable parsed sections.

#### Scenario: DOCX paragraphs are searchable
- **WHEN** parser 解析包含 paragraph 的 DOCX
- **THEN** paragraph 文本进入 parsed sections

#### Scenario: DOCX tables are searchable text
- **WHEN** parser 解析包含 table 的 DOCX
- **THEN** table cell 文本进入 parsed sections
- **AND** 不要求保留结构化 table schema

#### Scenario: DOCX headings preserve path
- **WHEN** DOCX 包含 heading paragraphs
- **THEN** sections metadata 保留 heading path

### Requirement: PPTX parser
knowledge-base SHALL parse PowerPoint slide text into sections with slide metadata.

#### Scenario: PPTX slides become sections
- **WHEN** parser 解析 PPTX
- **THEN** 每个包含文本的 slide 生成 section
- **AND** section metadata 包含 `slide_number`

#### Scenario: PPTX title is used when available
- **WHEN** slide 包含标题文本
- **THEN** section title 使用 slide title
- **AND** 没有标题时使用 `Slide N`

### Requirement: XLSX parser
knowledge-base SHALL parse Excel workbook cell text into searchable sections with sheet metadata.

#### Scenario: XLSX sheets become sections
- **WHEN** parser 解析 XLSX
- **THEN** 每个 non-empty sheet 生成 section
- **AND** section metadata 包含 `sheet_name`

#### Scenario: XLSX cells become searchable text
- **WHEN** sheet 包含非空 cells
- **THEN** cell values 以可检索文本形式进入 section
- **AND** 不要求保留结构化 table schema 或公式计算结果

### Requirement: Advanced local source parsing
local directory source SHALL include PDF, DOCX, PPTX and XLSX files in sync planning and parse them through the parser registry.

#### Scenario: Local source supports advanced extensions
- **WHEN** local directory 包含 `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** planner 将这些文件识别为 supported files

#### Scenario: Local sync parses advanced files
- **WHEN** executor 处理 advanced file ingest item
- **THEN** 它通过 parser registry 解析文件
- **AND** 调用 `ingest_parsed()` 写入 KB

#### Scenario: Advanced section metadata reaches chunks
- **WHEN** advanced parsed section 生成 chunk
- **THEN** chunk metadata 保留 page、slide 或 sheet 等 section metadata

### Requirement: Google Drive advanced content parsing
Google Drive connector SHALL map Google Sheets, Google Slides and uploaded Office/PDF files into the parser registry.

#### Scenario: Google Sheets export uses XLSX parser
- **WHEN** connector 同步 Google Sheets
- **THEN** 它通过 Drive export API 导出 `.xlsx`
- **AND** 调用 xlsx parser 生成 parsed document

#### Scenario: Google Slides export uses PPTX parser
- **WHEN** connector 同步 Google Slides
- **THEN** 它通过 Drive export API 导出 `.pptx`
- **AND** 调用 pptx parser 生成 parsed document

#### Scenario: Uploaded PDF and Office files use registry
- **WHEN** connector 同步 uploaded `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** 它 download 原始 bytes
- **AND** 通过 parser registry 解析

#### Scenario: Per-file export failure is isolated
- **WHEN** Google Drive export 或 download 某个文件失败
- **THEN** executor 记录 failed count 和脱敏错误摘要
- **AND** 继续处理后续 item
- **AND** 不记录文件正文或 credential

### Requirement: Advanced parser exclusions
knowledge-base advanced parsers SHALL keep OCR, VLM, scanned PDF, encrypted file parsing and structured table QA out of scope.

#### Scenario: OCR and VLM remain unsupported
- **WHEN** parser 遇到只能通过 OCR 或 VLM 理解的内容
- **THEN** parser 不调用 OCR、VLM 或外部解析服务
- **AND** 返回 unsupported / empty extraction failure

#### Scenario: Structured table QA remains out of scope
- **WHEN** parser 解析 DOCX 或 XLSX table
- **THEN** parser 只输出可检索文本
- **AND** 不输出 table QA 专用结构化模型

### Requirement: Knowledge-base entity extraction schema
knowledge-base SHALL store entity extraction runs, canonical entities, entity mentions and relations in SQLite tables owned by the knowledge-base capability.

#### Scenario: Extraction tables exist after migration
- **WHEN** Alembic upgrade 到 head
- **THEN** 数据库包含 `kb_extraction_runs`
- **AND** 包含 `kb_entities`
- **AND** 包含 `kb_entity_mentions`
- **AND** 包含 `kb_relations`

#### Scenario: Entity dedupe key is scoped
- **WHEN** schema 创建 `kb_entities`
- **THEN** `(tenant_id, kb_id, entity_type, normalized_name)` 是唯一键
- **AND** 同名实体不会跨 KB 合并

### Requirement: Entity and relation type boundaries
knowledge-base SHALL use a fixed first-version set of entity and relation types for extraction output.

#### Scenario: Supported entity types
- **WHEN** extractor 输出 entity
- **THEN** entity_type 必须是 `person`、`team`、`organization`、`customer`、`project`、`system`、`document`、`concept` 或 `term`

#### Scenario: Supported relation types
- **WHEN** extractor 输出 relation
- **THEN** relation_type 必须是 `mentions`、`belongs_to`、`owns`、`depends_on`、`related_to`、`defines` 或 `conflicts_with`

#### Scenario: Unsupported extraction type fails fast
- **WHEN** extractor 输出未知 entity_type 或 relation_type
- **THEN** extraction validation fail fast
- **AND** 不写入 invalid row

### Requirement: Entity normalization and scoped upsert
knowledge-base SHALL normalize entity names and upsert canonical entities within a tenant + KB + type scope.

#### Scenario: Same normalized entity merges in one KB
- **WHEN** extraction 在同一 tenant + KB 中看到同类型 `Customer A` 和 `customer a`
- **THEN** 系统只保留一个 canonical entity

#### Scenario: Same normalized entity does not merge across KBs
- **WHEN** extraction 在不同 KB 中看到同类型同名 entity
- **THEN** 系统创建不同 canonical entities

### Requirement: Explicit entity extraction runs
knowledge-base SHALL run entity extraction only through an explicit extraction run, not as a default side effect of ingest or sync.

#### Scenario: Document extraction run
- **WHEN** 调用方显式对一个 document 运行 extraction
- **THEN** 系统只扫描该 document 的 chunks
- **AND** 写入 extraction run summary、entities、mentions 和 relations

#### Scenario: Knowledge-base extraction run
- **WHEN** 调用方显式对一个 KB 运行 extraction
- **THEN** 系统逐 document 扫描该 KB 的 chunks
- **AND** 单 document 失败不阻止后续 document
- **AND** run summary 记录 failed count

#### Scenario: Ingest does not auto-extract
- **WHEN** KB ingest 或 connector sync 写入 document / chunks
- **THEN** 系统不默认运行 entity extraction

### Requirement: Document-level replacement semantics
knowledge-base entity extraction SHALL replace active mentions and relations for a document only after that document extraction succeeds.

#### Scenario: Successful rerun replaces document evidence
- **WHEN** 对同一个 document 重新运行 extraction 且成功
- **THEN** 系统替换该 document 旧 mentions 和 relations
- **AND** 保留历史 `kb_extraction_runs` summary

#### Scenario: Failed rerun keeps previous evidence
- **WHEN** 对同一个 document 重新运行 extraction 失败
- **THEN** 系统不删除该 document 旧 active mentions 或 relations
- **AND** run summary 记录失败摘要

#### Scenario: Orphan entity cleanup is deferred
- **WHEN** document replacement 后某 entity 暂时没有 mentions
- **THEN** 本 change 不要求立即删除 entity
- **AND** orphan cleanup 留给后续 maintenance

### Requirement: Deterministic extractor
knowledge-base SHALL provide a deterministic extractor for tests and default local execution.

#### Scenario: Deterministic extractor produces entities
- **WHEN** deterministic extractor 处理固定 fixture
- **THEN** 它输出符合 schema 的 customer、project、system、team、concept 或 term entities

#### Scenario: Deterministic extractor produces relations
- **WHEN** deterministic extractor 处理固定 relation fixture
- **THEN** 它输出符合 schema 的 `depends_on`、`defines` 或 `conflicts_with` relations
- **AND** 每条 relation 包含 source chunk evidence

### Requirement: Extraction evidence
knowledge-base SHALL keep source evidence for entity mentions and relations.

#### Scenario: Entity mention keeps evidence
- **WHEN** extraction 写入 entity mention
- **THEN** mention 包含 document_id、chunk_id、text、confidence 和 extraction_run_id

#### Scenario: Relation keeps evidence
- **WHEN** extraction 写入 relation
- **THEN** relation 包含 source_entity_id、target_entity_id、evidence_document_id、evidence_chunk_id、evidence_text、confidence 和 extraction_run_id

#### Scenario: Evidence is summarized
- **WHEN** extraction 保存 evidence_text
- **THEN** evidence_text 不包含完整文档正文

### Requirement: Entity extraction public API and CLI
knowledge-base SHALL expose explicit entity extraction through public API and admin CLI.

#### Scenario: Public API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 entity extraction models 和 `run_entity_extraction`
- **THEN** 导入成功

#### Scenario: Admin CLI triggers extraction
- **WHEN** operator 运行 `fleetent-admin kb extract-entities --kb-id <kb_id>`
- **THEN** CLI 调用 KB-level explicit extraction run
- **AND** 输出脱敏 run summary

#### Scenario: Admin CLI supports document scope
- **WHEN** operator 运行 `fleetent-admin kb extract-entities --kb-id <kb_id> --document-id <document_id>`
- **THEN** CLI 调用 document-level explicit extraction run
- **AND** 输出脱敏 run summary

### Requirement: Optional LLM extractor smoke
knowledge-base MAY provide a real LLM extractor smoke path, but it SHALL be explicitly opt-in and skipped by default.

#### Scenario: Real LLM extraction smoke is skipped by default
- **WHEN** 未设置 `FLEETENT_KB_ENTITY_EXTRACTION_REAL_LLM=1`
- **THEN** real LLM extraction smoke 被 skip

#### Scenario: Real LLM extraction requires provider config
- **WHEN** 设置 opt-in 但 provider config 或 credential 缺失
- **THEN** real LLM extraction smoke 被 skip
- **AND** 不影响默认测试

### Requirement: Entity extraction exclusions
knowledge-base entity extraction SHALL NOT implement graph search, automatic sync integration, scheduler, entity merge review or document ACL.

#### Scenario: Graph search remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** `search()` 和 hybrid ranking 不因 entities / relations 改变
- **AND** 不新增 graph traversal search

#### Scenario: Scheduler remains out of scope
- **WHEN** entity extraction change 完成
- **THEN** extraction 不自动进入 scheduler 或 worker
- **AND** 只通过 explicit run 触发

### Requirement: Knowledge-base graph search public API
knowledge-base SHALL provide an independent graph search API that returns chunks with graph evidence without changing existing `search()` behavior.

#### Scenario: Graph search API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `graph_search`、`GraphSearchResult`、`GraphSearchChunk`、`EntityRef` 和 `RelationRef`
- **THEN** 导入成功

#### Scenario: Graph search is independent from search
- **WHEN** 调用 `graph_search(...)`
- **THEN** 系统不改变 `search(..., mode=\"vector\")`、`search(..., mode=\"keyword\")` 或 `search(..., mode=\"hybrid\")` 的行为

#### Scenario: Graph search returns wrapper results
- **WHEN** graph search 返回 chunks
- **THEN** 每个结果包含 `KnowledgeChunk`
- **AND** 包含 graph_score、reason、matched_entities、relations 和 evidence_chunk_ids

### Requirement: Deterministic graph entity matching
graph search SHALL match query text to entities using deterministic normalized string matching.

#### Scenario: Entity name match
- **WHEN** normalized query contains an entity normalized_name
- **THEN** graph search treats that entity as matched

#### Scenario: Entity alias match
- **WHEN** entity metadata contains aliases
- **AND** normalized query contains one alias
- **THEN** graph search treats that entity as matched

#### Scenario: No semantic entity search
- **WHEN** graph search matches entities
- **THEN** it does not call LLM, embedding search, rerank provider or vector store for entity linking

### Requirement: Graph search depth
graph search SHALL support depth 0 and depth 1 only.

#### Scenario: Depth zero returns direct entity mentions
- **WHEN** graph search runs with `depth=0`
- **THEN** it returns chunks containing direct mentions of matched entities
- **AND** result reason is `direct_entity_match`

#### Scenario: Depth one expands relations
- **WHEN** graph search runs with `depth=1`
- **THEN** it returns direct entity mention chunks
- **AND** relation evidence chunks
- **AND** related entity mention chunks allowed by relation direction

#### Scenario: Depth greater than one fails fast
- **WHEN** graph search runs with `depth > 1`
- **THEN** it fails fast

### Requirement: Direction-aware relation expansion
graph search SHALL expand relations according to relation type direction.

#### Scenario: Bidirectional relations expand both ways
- **WHEN** matched entity participates in `related_to` or `conflicts_with`
- **THEN** graph search can expand to the other entity from either side

#### Scenario: Directional relations expand source to target
- **WHEN** matched entity is the source of `depends_on`、`belongs_to`、`owns` or `defines`
- **THEN** graph search can expand to the target entity

#### Scenario: Directional relations do not reverse expand
- **WHEN** matched entity is the target of `depends_on`、`belongs_to`、`owns` or `defines`
- **THEN** graph search does not expand back to the source entity

#### Scenario: Mentions relation does not expand
- **WHEN** matched entity participates in `mentions`
- **THEN** graph search does not use that relation for related entity expansion

### Requirement: Graph search scoring and dedupe
graph search SHALL rank deterministic graph candidates by reason score and stable chunk ordering.

#### Scenario: Graph reason scores
- **WHEN** graph search scores candidates
- **THEN** direct entity match has score `1.0`
- **AND** relation evidence has score `0.8`
- **AND** related entity mention has score `0.6`

#### Scenario: Duplicate chunk merges evidence
- **WHEN** the same chunk is reached through multiple graph paths
- **THEN** graph search returns it once
- **AND** keeps the highest graph_score
- **AND** merges matched_entities、relations and evidence_chunk_ids

#### Scenario: Stable graph ordering
- **WHEN** graph search returns multiple chunks
- **THEN** results are ordered by graph_score DESC、chunk position ASC、chunk id ASC

#### Scenario: Limit is applied after merge
- **WHEN** graph search has more candidates than limit
- **THEN** final returned chunks do not exceed limit

### Requirement: Graph search scope isolation
graph search SHALL respect tenant and KB scope and exclude archived documents.

#### Scenario: Tenant and KB scoped reads
- **WHEN** graph search runs for tenant A and kb X
- **THEN** it only reads entities、mentions、relations and chunks from tenant A and kb X

#### Scenario: Multiple KBs are allowed
- **WHEN** graph search runs with multiple kb_ids
- **THEN** it can combine graph candidates from those KBs within the same tenant

#### Scenario: Archived documents are excluded
- **WHEN** graph evidence points to archived document chunks
- **THEN** graph search does not return those chunks

### Requirement: Graph search evaluation
knowledge-base SHALL include deterministic evaluation fixtures for graph search behavior.

#### Scenario: Direct entity evaluation
- **WHEN** evaluation query mentions a customer entity
- **THEN** expected customer chunks appear in graph search results
- **AND** forbidden other-customer chunks do not appear

#### Scenario: One-hop relation evaluation
- **WHEN** evaluation query matches an entity with a one-hop relation
- **THEN** direct mention、relation evidence and related entity mention chunks appear as expected

#### Scenario: Relation direction evaluation
- **WHEN** evaluation query matches the target of a directional relation
- **THEN** graph search does not return source chunks through reverse expansion
- **AND** bidirectional relations still expand both ways

### Requirement: Graph search exclusions
graph search SHALL NOT implement query planner, rerank integration, semantic entity search, LLM query understanding, document ACL or multi-hop graph traversal.

#### Scenario: Planner remains out of scope
- **WHEN** graph search change 完成
- **THEN** 系统不自动决定何时调用 graph search
- **AND** query planner 留给后续 spec

#### Scenario: Rerank remains out of scope
- **WHEN** graph search 返回 candidates
- **THEN** 它不调用 rerank provider

#### Scenario: Document ACL remains out of scope
- **WHEN** graph search 读取 graph evidence
- **THEN** 它只按 tenant + KB scope 过滤
- **AND** 不实现 document-level ACL

### Requirement: Hybrid rerank opt-in
系统 SHALL 支持显式开启的 hybrid rerank，用 configured rerank provider 对 hybrid candidates 重排。

#### Scenario: Hybrid rerank is opt-in
- **WHEN** 调用 `search(query, mode="hybrid", rerank=True, limit=10)`
- **THEN** 系统先生成 hybrid candidates
- **AND** 调用 configured rerank provider 对 candidates 重排
- **AND** 返回数量不超过 10

#### Scenario: Existing search behavior remains default
- **WHEN** 调用 `search(query, mode="hybrid")`
- **THEN** 系统返回原 hybrid fused ranking
- **AND** 不调用 rerank provider

#### Scenario: Rerank only supports hybrid mode
- **WHEN** 调用 `search(query, mode="vector", rerank=True)` 或 `search(query, mode="keyword", rerank=True)`
- **THEN** 系统 fail fast
- **AND** 不调用 rerank provider

#### Scenario: Non-positive limit short-circuits
- **WHEN** 调用 `search(query, mode="hybrid", rerank=True, limit=0)`
- **THEN** 系统返回空列表
- **AND** 不调用 rerank provider

### Requirement: Hybrid rerank candidate pool
系统 SHALL 在 hybrid rerank 开启时扩大候选池，再返回 requested limit 内的结果。

#### Scenario: Candidate pool uses stable code constants
- **WHEN** `limit` 为 K 且 `rerank=True`
- **THEN** candidate pool size 等于 `min(max(K * 5, 20), 100)`
- **AND** 这些数值由 knowledge-base runtime 常量定义，不新增配置项

#### Scenario: Candidate pool feeds rerank provider
- **WHEN** hybrid rerank 执行
- **THEN** vector 和 keyword retrieval 使用 candidate pool size 生成 candidates
- **AND** rerank provider 接收按原 hybrid ranking 排序的 candidate content
- **AND** rerank provider 的 `top_n` 为 requested limit

### Requirement: Hybrid rerank result mapping
系统 SHALL 将 rerank provider 返回的 index + score 映射回 `KnowledgeChunk`，并保持结果稳定可解释。

#### Scenario: Provider order wins for valid indexes
- **WHEN** rerank provider 返回合法 indexes
- **THEN** 这些 chunks 按 provider 输出顺序排在前面
- **AND** 对应 `KnowledgeChunk.score` 使用 provider rerank score

#### Scenario: Illegal or duplicate provider indexes are ignored
- **WHEN** rerank provider 返回越界 index、负数 index 或重复 index
- **THEN** 系统忽略非法或重复项
- **AND** 继续处理其他有效结果

#### Scenario: Missing candidates are appended in hybrid order
- **WHEN** rerank provider 返回的有效结果少于 requested limit
- **THEN** 未被 provider 返回的 candidates 按原 hybrid order 追加
- **AND** 追加 chunks 保留原 hybrid score

### Requirement: Hybrid rerank failure fallback
系统 SHALL 在 rerank provider 不可用或失败时返回原 hybrid ranking，而不是让 search 失败。

#### Scenario: Disabled rerank provider falls back
- **WHEN** `rerank=True` 但 configured rerank provider disabled
- **THEN** 系统返回原 hybrid ranking
- **AND** 记录 structured warning

#### Scenario: Rerank provider error falls back
- **WHEN** rerank provider timeout、抛出 provider error 或返回无法使用的结果
- **THEN** 系统返回原 hybrid ranking
- **AND** 记录 structured warning

#### Scenario: Runtime event is emitted when available
- **WHEN** rerank fallback 发生且当前 runtime event boundary 可用
- **THEN** 系统 SHOULD 记录 `kb_rerank_failed` event
- **AND** 事件包含 tenant_id、kb_ids、limit、candidate_count 和 failure reason

### Requirement: Reranked knowledge-base retrieval evaluation
系统 SHALL 提供 deterministic evaluation coverage，用于验证 rerank 能改善 KB retrieval 排序。

#### Scenario: Deterministic rerank promotes expected chunk
- **WHEN** evaluation fixture 启用 deterministic rerank
- **THEN** expected chunk 出现在 top results 中
- **AND** 排名高于 rerank 前的干扰候选

#### Scenario: Forbidden chunks are not promoted
- **WHEN** evaluation fixture 包含 forbidden chunks
- **THEN** reranked results 的 top result 不包含 forbidden chunk

#### Scenario: Real rerank evaluation is opt-in
- **WHEN** 未显式开启 real rerank evaluation 环境变量
- **THEN** 不调用真实 rerank provider

### Requirement: Knowledge search planner public API
系统 SHALL 提供独立的规则型 knowledge search planner，用于解释并执行 KB retrieval 策略。

#### Scenario: Planner API is importable
- **WHEN** 调用方从 `fleetent.intelligence.knowledge_base` 导入 `KnowledgeSearchOptions`、`KnowledgeSearchPlan`、`KnowledgeSearchStep`、`plan_knowledge_search` 和 `execute_knowledge_search_plan`
- **THEN** 导入成功

#### Scenario: Planner does not change existing search API
- **WHEN** 调用 `search(..., mode="vector")`、`search(..., mode="keyword")` 或 `search(..., mode="hybrid")`
- **THEN** 行为保持对应底层检索语义
- **AND** 系统不要求使用 planner

#### Scenario: Planner does not use LLM
- **WHEN** `plan_knowledge_search()` 执行
- **THEN** 系统不调用 LLM、model router 或 query rewrite provider

### Requirement: Rule-based knowledge search planning
planner SHALL 使用 deterministic rules 生成带 reason 的 retrieval steps。

#### Scenario: Default query uses hybrid
- **WHEN** query 没有实体或关系迹象
- **THEN** plan 包含 `hybrid_search` step
- **AND** reason 包含 `default_hybrid`

#### Scenario: Entity or relation query uses graph first
- **WHEN** query 包含实体或关系迹象
- **THEN** plan 包含 `graph_search` step
- **AND** reason 包含 `entity_like_query` 或 `relation_like_query`

#### Scenario: Graph plan includes hybrid fill
- **WHEN** plan 包含 `graph_search`
- **THEN** plan 也包含 `hybrid_fill`
- **AND** `hybrid_fill` 用于 graph 结果不足 requested limit 时补齐

#### Scenario: Rerank option affects hybrid only
- **WHEN** `KnowledgeSearchOptions.rerank=True`
- **THEN** plan 中 hybrid 相关 step 标记 rerank
- **AND** graph step 不标记 rerank

### Requirement: Knowledge search plan execution
系统 SHALL 能执行 planner 输出的 steps，并返回去重后的检索结果。

#### Scenario: Execute default hybrid plan
- **WHEN** 执行只包含 `hybrid_search` 的 plan
- **THEN** 系统调用 hybrid search
- **AND** 透传 query、tenant_id、kb_ids 和 limit

#### Scenario: Execute graph with hybrid fill
- **WHEN** 执行包含 `graph_search` 和 `hybrid_fill` 的 plan
- **THEN** 系统先执行 graph search
- **AND** graph 结果不足 limit 时执行 hybrid search 补齐

#### Scenario: Execution deduplicates chunks
- **WHEN** graph 和 hybrid 返回同一 chunk
- **THEN** 最终结果只包含一次该 chunk
- **AND** 保留 graph evidence 或 source reason

#### Scenario: Execution respects limit
- **WHEN** plan execution 返回结果
- **THEN** 数量不超过 plan limit

### Requirement: Planner observability
planner SHALL 输出可排查的 selected steps 和 reason 信号。

#### Scenario: Planner records decision reason
- **WHEN** `plan_knowledge_search()` 生成 plan
- **THEN** plan 中每个 step 包含 reason

#### Scenario: Executor records retrieval summary
- **WHEN** `execute_knowledge_search_plan()` 完成
- **THEN** 系统记录 selected steps、graph result count、hybrid fill count 和 rerank requested 状态的 structured event 或 log

### Requirement: Planner evaluation
系统 SHALL 提供 deterministic evaluation，验证 planner 对普通查询、关系查询和 rerank 查询的策略选择。

#### Scenario: Ordinary query fixture chooses hybrid
- **WHEN** evaluation 运行普通事实查询 fixture
- **THEN** planner 选择 hybrid search

#### Scenario: Relation query fixture chooses graph plus fill
- **WHEN** evaluation 运行关系型查询 fixture
- **THEN** planner 选择 graph search 和 hybrid fill

#### Scenario: Rerank fixture only reranks hybrid
- **WHEN** evaluation 运行 `rerank=True` fixture
- **THEN** hybrid step 使用 rerank
- **AND** graph step 不使用 rerank

### Requirement: Real connector HTTP clients
Knowledge-base connector operations SHALL use real external HTTP clients by default for enabled
Google Drive and Confluence connectors, while keeping fake clients available for tests through
explicit dependency injection.

#### Scenario: Google Drive operations use real client by default
- **WHEN** an enabled Google Drive connector has a readable credential reference
- **AND** `check_connector()` or `run_connector_sync()` is called without an injected test client
- **THEN** the operation uses Google Drive HTTP API requests for folder listing, file download, and
  Google-native export
- **AND** it does not silently substitute an empty fake client

#### Scenario: Confluence operations use real client by default
- **WHEN** an enabled Confluence connector has a readable credential reference
- **AND** `check_connector()` or `run_connector_sync()` is called without an injected test client
- **THEN** the operation uses Confluence Cloud HTTP API requests for configured space or page scope
- **AND** it does not silently substitute an empty fake client

#### Scenario: Test client injection remains deterministic
- **WHEN** tests pass `google_drive_client` or `confluence_client` explicitly
- **THEN** connector operations use the injected client
- **AND** no external HTTP request is made

#### Scenario: Real sync summary reflects remote content
- **WHEN** a real connector sync succeeds against a Pilot fixture containing supported documents
- **THEN** sync status summary includes non-zero scanned/planned/ingested counts
- **AND** active KB documents/chunks exist for the configured tenant and kb

#### Scenario: Credential payload is never exposed
- **WHEN** real connector check or sync fails
- **THEN** status, CLI output, and error summaries do not include token payloads, refresh tokens,
  client secrets, Authorization headers, or full document bodies

#### Scenario: Google Drive explicit environment credential fields
- **WHEN** Google Drive connector config sets `access_token_env`, `refresh_token_env`,
  `client_id_env`, and `client_secret_env`
- **THEN** the connector reads OAuth fields from those named environment variables
- **AND** Google token URI defaults to `https://oauth2.googleapis.com/token`
- **AND** the operator does not need to store or inject a JSON payload as one environment variable

#### Scenario: Confluence username and token environment references
- **WHEN** Confluence connector config sets `username_env`
- **THEN** connector operations resolve the username from that environment variable
- **AND** Confluence API token is resolved from `api_token_env`
- **AND** Platform YAML config does not need to contain the account email
