# provider-connectivity-test Specification

## Purpose
TBD - created by archiving change 2026-06-02-model-provider-management. Update Purpose after archive.
## Requirements
### Requirement: Lightweight connectivity test for a single provider
An admin SHALL be able to trigger a lightweight connectivity probe for a single provider, showing whether it is reachable, the handshake latency, and the returned model identifier. The probe SHALL NOT be counted toward outbound usage (no observability cost / token usage recorded). The probe entry is exposed by the model-router domain; this surface triggers it and renders the result.

#### Scenario: Add provider then test connectivity
- **WHEN** an admin adds an OpenAI-compatible provider pointing at a local Ollama endpoint and clicks "connectivity test" after filling base_url / model
- **THEN** the result shows reachability, handshake latency, and the returned model identifier; the test is not counted toward outbound usage, and only after it is reachable may the provider be attached to a task_type route

#### Scenario: Unreachable endpoint reported, not attached
- **WHEN** the connectivity test cannot reach or handshake with the endpoint
- **THEN** the failure (handshake error) is reported and the provider is not attached to any task_type route

#### Scenario: Test does not record outbound usage
- **WHEN** a connectivity test is run against a provider
- **THEN** no cost or token usage is recorded in observability for that probe

### Requirement: Connectivity test is role-gated
Triggering a connectivity test SHALL be restricted to `admin` / `built_in_admin`. A `viewer` MAY only view existing test results read-only.

#### Scenario: Viewer cannot trigger a test
- **WHEN** a viewer attempts to trigger a connectivity test
- **THEN** the control is hidden or the request returns 403; the viewer may only view the last result read-only

