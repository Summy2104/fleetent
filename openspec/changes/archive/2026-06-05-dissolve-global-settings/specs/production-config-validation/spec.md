## MODIFIED Requirements

### Requirement: Profile-aware config validation

The system SHALL provide a config validation entrypoint that checks runtime prerequisites for `dev`,
`pilot` and `production` profiles, validating the per-agent `agent.yaml`(治理/部署/智能层字段)rather
than the dissolved global `Settings` agent-runtime fields. Platform-level prerequisites (authoring DB
reachability) MAY still be checked from the slim platform `Settings`. Validation SHALL report each item
as pass, warning, skipped or error.

#### Scenario: Missing real smoke credentials in pilot
- **WHEN** validation runs with `--profile pilot` and real smoke credentials are absent
- **THEN** the related items are reported as skipped with clear reasons
- **AND** validation does not fail solely because optional real smoke credentials are absent

#### Scenario: Missing production dependency in production
- **WHEN** validation runs with `--profile production` and a required production dependency declared in
  `agent.yaml` is absent
- **THEN** the related item is reported as error

### Requirement: Secret-safe config scanning

The system SHALL scan config file sources and route definitions for suspicious inline secrets, covering
the per-agent `agent.yaml` (governance/deployment/intelligence fields and `connectors`) in addition to
route definitions. Secret-like values SHALL be reported as errors unless they are explicit placeholders or
`*_env`/`credential_ref` references. Secrets supplied by environment variables or other approved secret
injection paths SHALL NOT be reported as inline config secrets, and their values SHALL NOT be rendered.

#### Scenario: Inline API key is rejected
- **WHEN** an `agent.yaml` contains a secret-like API key value instead of an env/file credential reference
- **THEN** validation reports an error naming the config path and field

#### Scenario: Environment-provided secret is not an inline config error
- **WHEN** validation runs with provider or IM tokens supplied through environment variables referenced by
  `*_env` names in `agent.yaml`
- **THEN** validation does not report those env-backed values as inline config secrets
- **AND** validation output does not include the token values
