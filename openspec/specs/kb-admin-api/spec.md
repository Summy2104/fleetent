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

#### Scenario: Create KB and import a document (场景 103)
- **WHEN** an admin creates kb_id "support" in a tenant that has no such KB and pastes a Markdown document to import
- **THEN** the KB is created and the document is parsed, chunked, and indexed via the knowledge-base engine, appearing in the document list with its chunk count and ingest result, without a service restart
- **AND** the default server route returns a real `document_id` and non-zero chunk count rather than placeholder `wired: false` output

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

### Requirement: Document import via multiple entry points

An admin SHALL import documents by pasting / uploading text, Markdown, or lightweight HTML, and by configuring a local directory data source and manually triggering sync. The management plane SHALL enqueue execute-path ingest work via `kb-ingest-queue` before consuming it; it SHALL NOT keep the old direct `asyncio.run(...)` execute path in the route handler.

#### Scenario: Paste import enqueues before execution

- **WHEN** an admin pastes text/markdown/html content into a KB on a running local server
- **THEN** the system first enqueues a `kb_ingest_jobs` record for that import
- **AND** in the current transition phase it may consume that same job inline and return the real document id, chunk count, filename/source metadata

#### Scenario: Local directory sync enqueues before execution

- **WHEN** an admin configures a local directory source and triggers sync
- **THEN** the system first enqueues a `kb_ingest_jobs` record for that sync
- **AND** in the current transition phase it may consume that same job inline and return scanned / ingested / skipped / failed counts

#### Scenario: Full re-sync requires confirmation

- **WHEN** an admin triggers a full directory re-sync
- **THEN** the action requires a second confirmation and is audited (`doc_sync`)

### Requirement: Document list and lifecycle

The system SHALL list documents within a single KB (filename, source / source_url, chunk count, created time), allow previewing a document's chunks (content + section context), and allow deleting a single document. Deletion SHALL cascade to chunks and vector entries via the engine `delete(document_id)`.

#### Scenario: Document list reflects host-ingested content
- **WHEN** a document was imported through `/admin/kb/{kb_id}/documents`
- **THEN** `GET /admin/kb/{kb_id}/documents` returns that document with its real chunk count and source metadata

#### Scenario: Chunk preview shows section context
- **WHEN** an admin or viewer previews a document
- **THEN** each chunk shows its content and section context

#### Scenario: Delete cascades and is audited (场景 107)
- **WHEN** an admin deletes document D in a KB and confirms
- **THEN** D and its chunks and vector entries are removed via the engine, subsequent retrieval no longer returns D's content, and the deletion is audited (`doc_delete`)

### Requirement: Per-KB observation aggregation
The KB detail view SHALL present a per-kb aggregation of recall hit counts / trends, referencing sessions, and long-term zero-recall documents, with drill-down into referencing session traces. The data source is the observability domain; this plane only aggregates by kb.

#### Scenario: Per-KB recall aggregation is read-only
- **WHEN** an admin opens a KB's observation view
- **THEN** recall hit counts/trends and zero-recall documents are shown without modifying the index

### Requirement: Knowledge base management permissions and audit
KB / document creation, import, deletion, archive, and agent binding SHALL be admin-only. Viewers SHALL only browse KBs, documents, and retrieval test results. High-risk actions (delete KB, delete document, full directory re-sync) SHALL require a second confirmation. All write operations SHALL be audited.

#### Scenario: Viewer cannot manage knowledge bases (场景 108)
- **WHEN** a viewer opens the knowledge base management page and tries to create a KB, import a document, or delete a document
- **THEN** the controls are hidden or the request returns 403, and the viewer may only browse KBs, documents, and retrieval test results

#### Scenario: Write operations are audited
- **WHEN** an admin performs any KB or document write operation
- **THEN** an audit entry recording actor / action / target / detail is written

### Requirement: Manual KB entity extraction trigger

The system SHALL expose `POST /admin/kb/{kb_id}/extract-entities` on the existing KB admin router so an admin can manually trigger entity extraction for one KB, equivalent to `fleetent admin kb extract-entities`. The endpoint SHALL run through the existing KB runtime wiring and return `202 Accepted`.

#### Scenario: Trigger entity extraction for a KB
- **WHEN** an admin calls `POST /admin/kb/{kb_id}/extract-entities`
- **THEN** the system starts entity extraction for that KB and returns 202 Accepted

#### Scenario: Missing KB is rejected
- **WHEN** an admin calls the extract endpoint for a KB that does not exist or is archived
- **THEN** the system returns 404 and does not start extraction

#### Scenario: Viewer cannot trigger entity extraction
- **WHEN** a viewer calls `POST /admin/kb/{kb_id}/extract-entities`
- **THEN** the system returns 403

### Requirement: Connector sync 经队列异步执行

`kb_admin_api` 的 connector sync SHALL 经 `kb-ingest-queue` 入队执行。dry-run(仅出 plan、不写)可保持同步;execute(真实写)SHALL 先入队,再由当前过渡 drain 或后续 worker 消费。

#### Scenario: Execute sync 入队

- **WHEN** admin 调用 connector sync(execute,非 dry-run)
- **THEN** 端点先写入一条 ingest job
- **AND** 返回 job id(或入队+等完成的结果),而不是沿用旧的直连 execute 路径

#### Scenario: Dry-run 仍同步出 plan

- **WHEN** admin 调用 connector sync `--dry-run`
- **THEN** 端点同步返回 plan summary(不写、不入 execute 队列)

#### Scenario: 输出仍脱敏

- **WHEN** 端点返回 sync / 入队结果
- **THEN** 输出不含 token、secret、credential payload 或完整文档正文

