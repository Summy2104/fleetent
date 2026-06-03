# pilot-verification-gate Specification

## Purpose
TBD - created by archiving change pilot-verification-gate. Update Purpose after archive.
## Requirements
### Requirement: Pilot verification gate

The project SHALL provide a Pilot verification gate that runs or records required local checks, optional real
smoke checks, capability evidence and final Go / Conditional Go / No-Go recommendation.

#### Scenario: Required local check fails
- **WHEN** a required local check such as pytest, OpenSpec validation, module boundary check or config validation fails
- **THEN** the final recommendation is No-Go

#### Scenario: Optional real smoke is skipped
- **WHEN** required local checks pass but an optional real smoke is skipped due to missing opt-in flag or credentials
- **THEN** the report records the skipped reason
- **AND** the final recommendation follows issue classification rules instead of failing automatically

### Requirement: Gate report artifacts

The gate SHALL emit Markdown for human review and JSON for automation. Reports SHALL include command results,
capability evidence, config validation status, diagnostics artifact links, real smoke status and issue
classification.

#### Scenario: Report includes reproducible command evidence
- **WHEN** the gate report is generated
- **THEN** each command includes status, duration, command text and artifact path when available

