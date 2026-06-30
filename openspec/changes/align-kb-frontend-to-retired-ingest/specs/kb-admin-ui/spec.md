## MODIFIED Requirements

### Requirement: Knowledge Base managed natively in the React SPA

The React admin SPA SHALL render the Knowledge Base domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list / create / edit / delete knowledge bases; list and delete documents; and view an agent binding. This closes the legacy gap where KB definitions and bindings could only be managed via API/CLI.

The SPA SHALL NOT expose document ingest, directory sync, or KB connector management — those platform-side ingest controls were retired (`kb-retire-platform-ingest`); document ingestion now belongs to the standalone KB ingest service, not the platform admin UI.

#### Scenario: List and create knowledge bases

- **WHEN** an admin opens the KB view
- **THEN** knowledge bases are listed via `GET /admin/kb`, and creating one calls `POST /admin/kb` and refreshes the list

#### Scenario: List and remove documents

- **WHEN** an admin views a KB's documents or deletes one
- **THEN** the SPA calls `GET /admin/kb/{id}/documents` (resp. `DELETE /admin/kb/{id}/documents/{doc}`) and the document list refreshes

#### Scenario: Ingest, sync, and connectors are not in the SPA

- **WHEN** the KB view is rendered
- **THEN** there is no Connectors tab, no document-ingest control, and no directory-sync control
- **AND** the SPA makes no calls to `/admin/kb/connectors…`, `POST /admin/kb/{id}/documents`, or `POST /admin/kb/{id}/sync` (all retired backend endpoints)

#### Scenario: KB no longer deep-links to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Knowledge Base is a native route, not an entry in the legacy deep-link list
