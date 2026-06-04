## ADDED Requirements

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
- **AND** `settings.yaml` does not need to contain the account email
