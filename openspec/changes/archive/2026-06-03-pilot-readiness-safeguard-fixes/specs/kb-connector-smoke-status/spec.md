## MODIFIED Requirements

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
- **WHEN** an operator runs `fleetent-admin kb connectors sync <connector_id>` without `--dry-run`
- **AND** confirmation, execute opt-in or Pilot fixture acknowledgement is absent
- **THEN** the command exits before mutation
- **AND** prints the required dry-run or execute safeguard

#### Scenario: Manual execute sync safeguards are present
- **WHEN** an operator runs manual execute sync with `--yes`, execute opt-in and Pilot fixture acknowledgement
- **THEN** the sync operation may run
- **AND** latest connector status records the outcome with credentials redacted
