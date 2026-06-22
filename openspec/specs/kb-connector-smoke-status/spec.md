# kb-connector-smoke-status Specification

## Purpose
TBD - created by archiving change kb-connector-smoke-status. Update Purpose after archive.
## Requirements
### Requirement: Connector latest status

KB connector operations SHALL expose latest status for check, dry-run sync and execute sync attempts. Status
SHALL include source scope, timestamps, outcome, failure summary and skipped reason while redacting credentials.

#### Scenario: Credential reference is redacted
- **WHEN** latest status is rendered for a connector with credential_ref
- **THEN** the credential reference is redacted
- **AND** no credential payload or token value is shown

### Requirement: Real connector smoke is explicit opt-in

Google Drive and Confluence real smoke SHALL skip by default unless explicit opt-in flags and credential refs are
provided. Real execute sync SHALL require a separate opt-in beyond check and dry-run, and SHALL only run against
an explicitly marked Pilot fixture folder or space. Manual CLI execute sync SHALL enforce this boundary before
mutation by requiring confirmation, execute opt-in and Pilot fixture acknowledgement.

#### Scenario: Real execute sync is not enabled
- **WHEN** real connector smoke is enabled but execute sync opt-in is absent
- **THEN** check and dry-run may run
- **AND** execute sync is skipped with a clear reason

#### Scenario: Real execute sync source is not a Pilot fixture
- **WHEN** real connector smoke has execute sync opt-in enabled
- **AND** the configured source is not marked as a Pilot fixture
- **THEN** execute sync is skipped with a clear reason

#### Scenario: Manual execute sync lacks safeguards
- **WHEN** an operator calls `POST /admin/kb/connectors/<connector_id>/sync` without a dry-run body
- **AND** confirmation, execute opt-in or Pilot fixture acknowledgement is absent
- **THEN** the command exits before mutation
- **AND** prints the required dry-run or execute safeguard

#### Scenario: Manual execute sync safeguards are present
- **WHEN** an operator runs manual execute sync with `--yes`, execute opt-in and Pilot fixture acknowledgement
- **THEN** the sync operation may run
- **AND** latest connector status records the outcome with credentials redacted

### Requirement: Connector evidence in Pilot report

Pilot verification SHALL include connector status and real smoke pass/fail/skipped evidence.

#### Scenario: Connector smoke skipped
- **WHEN** connector smoke is skipped due to missing credentials
- **THEN** the report includes the skipped reason and does not classify it as an automatic local test failure
