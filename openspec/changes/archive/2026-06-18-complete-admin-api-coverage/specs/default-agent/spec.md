## MODIFIED Requirements

### Requirement: Admin can set default agent via CLI

The platform SHALL expose `PUT /admin/agents/{name}/default` (set the named agent as default) and `DELETE /admin/agents/default` (clear the current default). The default SHALL be a control-plane attribute persisted in the management DB (a single default agent per tenant), NOT edited directly on node-side `agent.yaml` files. Setting a new default SHALL clear any previously-default agent in the same tenant. The materialize path SHALL emit `bindings.default: true` into the agent.yaml content for the agent marked default, so node-side scan continues to resolve the default from `bindings.default` unchanged. Both endpoints MUST require admin role and write an audit entry.

The legacy CLI `set-default-agent` (which directly edited `agent.yaml` files) is superseded by these endpoints; it is removed by the `slim-admin-cli` change.

#### Scenario: Set default agent via HTTP

- **WHEN** admin calls `PUT /admin/agents/basic/default`
- **THEN** agent `basic` is marked default in the management DB, any previously-default agent in the tenant is cleared, and an audit entry is written

#### Scenario: Default propagates through materialize

- **WHEN** agent `basic` is marked default and the node pulls its materialized agent.yaml
- **THEN** the materialized content has `bindings.default: true` for `basic`, and node-side scan resolves `basic` as the default with no DB read

#### Scenario: Clear default agent via HTTP

- **WHEN** admin calls `DELETE /admin/agents/default`
- **THEN** no agent is marked default; materialize emits no `bindings.default: true`, and default resolution returns nothing

#### Scenario: Existing file-based default is backfilled

- **WHEN** the change is deployed on an install where an agent.yaml already has `bindings.default: true`
- **THEN** that agent's default flag is backfilled into the control-plane attribute, and the materialized output preserves `bindings.default: true` for the same agent (no behavior change before/after migration)

#### Scenario: Non-admin cannot set default

- **WHEN** a non-admin user calls `PUT /admin/agents/{name}/default` or `DELETE /admin/agents/default`
- **THEN** the system returns 403
