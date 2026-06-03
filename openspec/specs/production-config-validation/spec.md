# production-config-validation Specification

## Purpose
TBD - created by archiving change production-config-validation. Update Purpose after archive.
## Requirements
### Requirement: Profile-aware config validation

The system SHALL provide a config validation entrypoint that checks runtime prerequisites for `dev`,
`pilot` and `production` profiles. Validation SHALL report each item as pass, warning, skipped or error.

#### Scenario: Missing real smoke credentials in pilot
- **WHEN** validation runs with `--profile pilot` and real smoke credentials are absent
- **THEN** the related items are reported as skipped with clear reasons
- **AND** validation does not fail solely because optional real smoke credentials are absent

#### Scenario: Missing production dependency in production
- **WHEN** validation runs with `--profile production` and a required production dependency is absent
- **THEN** the related item is reported as error

### Requirement: Secret-safe config scanning

The system SHALL scan config file sources and route definitions for suspicious inline secrets. Secret-like values
in settings, routes or MCP config SHALL be reported as errors unless they are explicit placeholders or credential
references. Secrets supplied by environment variables or other approved secret injection paths SHALL NOT be
reported as inline config secrets, and their values SHALL NOT be rendered.

#### Scenario: Inline API key is rejected
- **WHEN** a config file contains a secret-like API key value instead of an env/file credential reference
- **THEN** validation reports an error naming the config path and field

#### Scenario: Environment-provided secret is not an inline config error
- **WHEN** validation runs with provider or IM tokens supplied through environment variables
- **THEN** validation does not report those env-backed values as inline config secrets
- **AND** validation output does not include the token values

### Requirement: Validation report output

The system SHALL expose validation results in human-readable and JSON output, and the Pilot verification
report SHALL include config validation status.

#### Scenario: JSON validation summary
- **WHEN** `fleetent-admin validate-config --profile pilot --format json` is run
- **THEN** it emits stable JSON with profile, item statuses, reasons and final status

