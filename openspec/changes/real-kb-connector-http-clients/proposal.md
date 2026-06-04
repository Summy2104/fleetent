## Why

Production-like intelligence roadmap validation found that `fleetent-admin kb connectors check/sync`
does not actually call Google Drive or Confluence APIs by default. `operations.py` falls back to
`FakeGoogleDriveClient` and `FakeConfluenceClient`, so a configured connector can report
`sync_succeeded` with an empty summary and zero KB documents.

That behavior is acceptable for unit tests, but it makes Pilot validation misleading: configured
credentials and scopes are not proven against the real external systems, and execute sync does not
ingest the remote fixture content.

## What Changes

- Add real HTTP client implementations for Google Drive and Confluence connector protocols.
- Wire connector operations to create real clients by default when no test client is injected.
- Keep fake clients available only for tests and explicit injection.
- Google Drive client supports:
  - OAuth token loaded via explicit env fields such as `access_token_env`,
    `refresh_token_env`, `client_id_env`, and `client_secret_env`.
  - access-token bearer auth.
  - refresh-token flow when token metadata contains refresh fields.
  - folder file listing, binary download, and Google-native export.
- Confluence client supports:
  - Cloud API token via `api_token_env`.
  - basic auth with configured `username` or `username_env`.
  - space page listing, page fetch, and child page listing.
- Persist meaningful sync summaries from real connector syncs.
- Preserve credential redaction and do not print token payloads.

## Out of Scope

- No new secret store, token rotation UI, OAuth browser flow, or credential creation command.
- No Google service account support unless the existing payload already yields a bearer token.
- No Confluence Server/Data Center support.
- No attachment/comment/blog sync expansion.
- No scheduler or background sync worker.
- No changes to observability roadmap validation.

## Module Boundary Impact

- **Owning package**: `intelligence.knowledge_base`.
- **Public API surface**: add real connector client classes/factories under
  `fleetent.intelligence.knowledge_base.connectors.google_drive` and `.confluence`; existing
  operations functions keep the same signatures and continue allowing test client injection.
- **Owned tables**: none.
- **Config namespace**: no new namespace; uses existing
  `knowledge_base.google_drive.connectors[]` and `knowledge_base.confluence.connectors[]`.
- **Cross-module dependencies**: connector clients depend on existing `httpx`, existing config
  dataclasses, existing credential ref readers, and existing KB sync APIs.
- **Migration / shim plan**: additive implementation only; fake clients remain for tests.
