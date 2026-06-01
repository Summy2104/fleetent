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
基础 parser SHALL 不引入 LlamaIndex、LangChain、docling、PDF/Office parser 或 VLM 依赖。

#### Scenario: No AI framework parser dependency
- **WHEN** basic parser change 完成
- **THEN** runtime dependency 不包含 LlamaIndex、LangChain 或 docling

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

### Requirement: Hybrid search excludes advanced retrieval
hybrid search SHALL NOT implement reranker, query planner, graph search or external search backend.

#### Scenario: No rerank dependency
- **WHEN** hybrid search 执行
- **THEN** 系统不调用 rerank provider

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
Google Drive connector SHALL map supported Drive content into existing knowledge-base parsers.

#### Scenario: Google Docs export uses HTML parser
- **WHEN** connector 同步 Google Docs
- **THEN** 它通过 Drive export API 导出 HTML
- **AND** 调用现有 HTML parser 生成 parsed document

#### Scenario: Plain text uses text parser
- **WHEN** connector 同步 plain text 文件
- **THEN** 它调用现有 text parser

#### Scenario: Markdown uses markdown parser
- **WHEN** connector 同步 Markdown 文件
- **THEN** 它调用现有 Markdown parser

#### Scenario: HTML file uses HTML parser
- **WHEN** connector 同步 HTML 文件
- **THEN** 它调用现有 HTML parser

#### Scenario: Google Sheets and Slides are unsupported in MVP
- **WHEN** connector 遇到 Google Sheets 或 Google Slides
- **THEN** 系统跳过该文件
- **AND** summary 记录 unsupported 数量

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
