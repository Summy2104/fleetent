## MODIFIED Requirements

### Requirement: Unit coverage threshold
CI SHALL enforce unit coverage thresholds for actively maintained first-party modules.

#### Scenario: Scoped unit coverage threshold
- **WHEN** CI runs scoped unit coverage checks
- **THEN** scoped unit coverage for `fleetent.intelligence`、`fleetent.observability`、`fleetent.config` 和 `scripts.upgrade` 至少达到 75%
