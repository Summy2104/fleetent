# kb-retrieval-playground Specification

## Purpose
TBD - created by archiving change 2026-06-02-knowledge-base-management. Update Purpose after archive.
## Requirements
### Requirement: Retrieval playground
The system SHALL provide a retrieval test bench `/admin/kb/search` taking a query, one or more selected kb_ids, a search mode (vector / keyword / hybrid), and a top-k. It SHALL orchestrate the engine `search` and return the recalled chunks. It SHALL NOT redefine retrieval; it orchestrates the engine. Both viewer and admin SHALL be able to run it and view results.

#### Scenario: Hybrid recall verification (场景 105)
- **WHEN** an admin enters a query in the playground, selects a KB that has imported documents, picks hybrid mode, and sets top-k=5
- **THEN** at most 5 recalled chunks are returned, each showing score, owning document, position, and section context, in stable score order

#### Scenario: Multiple knowledge bases selectable
- **WHEN** the query selects multiple kb_ids in the current tenant
- **THEN** the system passes all selected kb_ids to the engine search and merges the results

#### Scenario: Mode is passed to the engine
- **WHEN** the playground request specifies vector, keyword, or hybrid mode
- **THEN** the system calls the engine search with that mode unchanged

#### Scenario: Unknown mode fails fast
- **WHEN** an unsupported mode is supplied
- **THEN** the request fails fast and no search is performed

#### Scenario: Viewer can run the playground read-only
- **WHEN** a viewer runs a retrieval test
- **THEN** the recalled chunks and their scores are returned without any write to KB state

#### Scenario: Results carry no model answer
- **WHEN** the playground returns results
- **THEN** results contain only recalled chunks (recall test), complementing chat-management's end-to-end "chat dry run"

