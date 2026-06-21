## ADDED Requirements

### Requirement: Agent-owned periodic reflection trigger

The agent runtime SHALL provide a process-internal periodic background loop that calls `run_reflection` on a configurable interval, so reflection runs without depending on the platform CLI. The trigger SHALL be config-gated and **default OFF (per-agent opt-in)**: an agent-level reflection config exposes `enabled` (default false) and `interval_seconds` (configurable). The loop SHALL be bulkheaded — a single `run_reflection` failure is logged and the loop continues (it MUST NOT change the process exit code or affect other components). It SHALL start at agent boot only when enabled, stop (cancel without residue) at shutdown, and be idempotent on start. Triggering only **generates** proposals; applying them still requires the existing (agent-owned, DM-delivered) approval — consistent with "No automatic application".

#### Scenario: Disabled by default is a no-op

- **WHEN** an agent boots with reflection config left at defaults
- **THEN** no reflection loop is started and behavior is unchanged from before this capability

#### Scenario: Enabled agent triggers reflection on its interval

- **WHEN** an agent is configured with reflection `enabled = true` and an `interval_seconds`
- **THEN** the runtime starts a background loop that calls `run_reflection` for that agent each interval

#### Scenario: A failed cycle does not kill the loop

- **WHEN** one `run_reflection` invocation raises
- **THEN** the failure is logged, the process exit code is unchanged, and the next interval still triggers a reflection run

#### Scenario: Start is idempotent and stop leaves no residue

- **WHEN** the reflection scheduler is started while already running, then stopped
- **THEN** starting returns the existing task (no duplicate), and stopping cancels it with no leftover task

#### Scenario: Triggering still does not auto-apply

- **WHEN** a triggered reflection run produces a `skill_opportunity` finding
- **THEN** no `skills/` files are created/updated/deleted by the trigger itself; application remains approval-gated

### Requirement: Applying a skill proposal reloads the agent skill registry

When a skill proposal is applied (post-approval) via `apply_skill_proposal_to_boundary`, the agent runtime SHALL reload its skill registry after the write so the change takes effect in the running agent without a restart, reusing the existing hot-reload atomic-swap semantics.

#### Scenario: Applied skill change is live in-session

- **WHEN** an approved skill proposal is applied and the skill files are written
- **THEN** the agent reloads its skill registry, and the updated skill is available to subsequent turns without restarting the agent

#### Scenario: Reload failure preserves the old index

- **WHEN** the post-apply reload fails
- **THEN** the existing hot-reload behavior is preserved (old index kept and a warning emitted), not a half-empty index
