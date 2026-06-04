## MODIFIED Requirements

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

### Requirement: Document import via multiple entry points

An admin SHALL import documents by pasting / uploading text, Markdown, or lightweight HTML (orchestrating the engine `ingest_text` / `parse_*`), and by configuring a local directory data source and manually triggering sync (orchestrating `sync_local_directory`). The management plane SHALL NOT redefine chunking or indexing; it orchestrates the engine.

#### Scenario: Paste import orchestrates ingest
- **WHEN** an admin pastes text/markdown/html content into a KB on a running local server
- **THEN** the system calls the engine ingest API with the current tenant_id and kb_id
- **AND** the response returns the real document id, chunk count, filename/source metadata and no `wired: false` placeholder

#### Scenario: Local directory sync returns a summary
- **WHEN** an admin configures a local directory source and triggers sync
- **THEN** the system calls the engine local sync and returns scanned / ingested / skipped / failed counts

#### Scenario: Full re-sync requires confirmation
- **WHEN** an admin triggers a full directory re-sync
- **THEN** the action requires a second confirmation and is audited (`doc_sync`)

#### Scenario: Viewer cannot import
- **WHEN** a viewer attempts to import a document or trigger sync
- **THEN** the request returns 403

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
