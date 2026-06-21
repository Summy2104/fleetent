## ADDED Requirements

### Requirement: Knowledge Base managed natively in the React SPA

The React admin SPA SHALL render the Knowledge Base domain natively (not a deep-link to legacy) and SHALL support, against the existing admin API: list / create / edit / delete knowledge bases; ingest, list, and delete documents; trigger a sync; manage KB connectors (register, edit, delete, check, view status, sync); and view an agent binding. This closes the legacy gap where KB content could only be managed via API/CLI.

#### Scenario: List and create knowledge bases

- **WHEN** an admin opens the KB view
- **THEN** knowledge bases are listed via `GET /admin/kb`, and creating one calls `POST /admin/kb` and refreshes the list

#### Scenario: Ingest and remove documents

- **WHEN** an admin ingests a document into a KB, or deletes one
- **THEN** the SPA calls `POST /admin/kb/{id}/documents` (resp. `DELETE /admin/kb/{id}/documents/{doc}`) and the document list refreshes

#### Scenario: Manage a KB connector

- **WHEN** an admin registers a KB connector and runs a check / sync
- **THEN** the SPA calls the matching `/admin/kb/connectors…` endpoints and reflects status/result

#### Scenario: KB no longer deep-links to legacy

- **WHEN** the SPA navigation is rendered
- **THEN** Knowledge Base is a native route, not an entry in the legacy deep-link list
