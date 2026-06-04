## 1. Google Drive real HTTP client

- [x] 1.1 Write failing tests: real Google client lists Drive files from the configured folder using bearer auth and maps Drive metadata into `GoogleDriveFile`.
- [x] 1.2 Write failing tests: real Google client downloads binary files and exports Google-native docs/sheets/slides through Drive API endpoints.
- [x] 1.3 Write failing tests: expired OAuth token JSON with refresh metadata refreshes the access token without logging credential payload.
- [x] 1.4 Write failing tests: Google Drive connector config loads explicit env fields such as `access_token_env`, `refresh_token_env`, `client_id_env`, and `client_secret_env`, with Google token URI defaulted by code.
- [x] 1.5 Implement: `HttpGoogleDriveClient` and token resolver using `httpx`.
- [x] 1.6 Verify green: run `uv run pytest tests/unit/test_google_drive_connector.py -x -q`.

## 2. Confluence real HTTP client

- [x] 2.1 Write failing tests: real Confluence client lists space pages with storage/version/space/ancestor expansion and pagination.
- [x] 2.2 Write failing tests: real Confluence client fetches one page and lists child pages using configured username/token basic auth.
- [x] 2.3 Write failing tests: Confluence connector config can use `username_env` and `api_token_env` so usernames and API tokens do not need to live in `settings.yaml`.
- [x] 2.4 Write failing tests: 401/403 maps to `ConfluenceAuthError`, 429 maps to `ConfluenceRateLimitError`, and non-auth HTTP errors are surfaced without token payload.
- [x] 2.5 Implement: `HttpConfluenceClient` using `httpx`.
- [x] 2.6 Verify green: run `uv run pytest tests/unit/test_confluence_connector.py -x -q`.

## 3. Operations default wiring

- [x] 3.1 Write failing tests: `check_connector()` without injected clients creates real clients instead of fake clients.
- [x] 3.2 Write failing tests: `run_connector_sync()` without injected clients creates real clients and preserves real sync summary counts.
- [x] 3.3 Implement: connector operations real-client factories while preserving fake injection for tests.
- [x] 3.4 Verify green: run `uv run pytest tests/unit/test_knowledge_connector_operations.py tests/integration/test_knowledge_connector_operations.py -x -q`.

## 4. Production validation

- [x] 4.1 Run default related tests: `uv run pytest tests/unit/test_google_drive_connector.py tests/unit/test_confluence_connector.py tests/unit/test_knowledge_connector_operations.py tests/integration/test_knowledge_connector_operations.py -x -q`.
- [x] 4.2 Run strict OpenSpec validation: `openspec validate real-kb-connector-http-clients --strict`.
- [x] 4.3 Run real configured connector checks with local env loaded.
- [x] 4.4 Run real configured connector dry-run and execute sync against Pilot fixtures.
- [x] 4.5 Verify local KB document/chunk counts and keyword search results without printing document body.
- [x] 4.6 Run final related/full validation appropriate to touched scope.
