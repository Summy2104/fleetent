# model-pricing-table Specification

## Purpose
TBD - created by archiving change 2026-06-02-model-provider-management. Update Purpose after archive.
## Requirements
### Requirement: Per-model input/output unit price maintenance
An admin SHALL be able to maintain, per model, the input and output unit price per 1k tokens. The price table lives in the model_router configuration (alongside provider / model declarations, operator-maintained). Changing a price SHALL be audited.

#### Scenario: Maintain unit prices for a model
- **WHEN** an admin sets input and output per-1k-token prices for a model
- **THEN** the prices are persisted into the model_router configuration and the change is written to the audit log

### Requirement: Cost aggregation uses token × price
Configured unit prices SHALL be used by the statistics panel / observability to aggregate cost as `token × price`.

#### Scenario: Cost computed from configured price
- **WHEN** a model has configured input/output prices and accrues token usage
- **THEN** cost is aggregated as `token × price` using those configured prices

### Requirement: Unconfigured price shows "not configured" not 0
A model with no configured unit price SHALL show "not configured" in cost views rather than 0, and the management page SHALL highlight such models' price entries. A configured price of 0 SHALL be distinguishable from an unconfigured (missing) price.

#### Scenario: Self-hosted model without price shows "not configured"
- **WHEN** a self-hosted model has no maintained unit price and the statistics panel shows a cost view including that model
- **THEN** the model's cost shows "not configured" rather than 0, and the model_provider management page highlights that model's price entry

#### Scenario: Explicit zero differs from missing
- **WHEN** one model has price explicitly set to 0 and another has no price configured
- **THEN** the first aggregates as $0 cost while the second shows "not configured"

### Requirement: Price maintenance is role-gated
Maintaining the model price table SHALL be restricted to `admin` / `built_in_admin`. A `viewer` SHALL only view prices and resulting cost views.

#### Scenario: Viewer cannot edit prices
- **WHEN** a viewer attempts to change a model's unit price
- **THEN** the controls are hidden or the request returns 403

