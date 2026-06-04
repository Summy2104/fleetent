## MODIFIED Requirements

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
