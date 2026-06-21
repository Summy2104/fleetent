# Migration: per-agent sandbox config

Sandbox resource/hardening/lifecycle/skills-mount config moved off the machine-shared
`platform.yaml` onto each agent's `agent.yaml`, so every agent owns its own sandbox
profile and a direct `fleetent agent run` process no longer depends on `platform.yaml` for these settings
(`per-agent-sandbox-resources`).

## What moved

| Old `platform.yaml` (shared) | New `agent.yaml` (per-agent) |
|---|---|
| `sandbox.resources.*` (memory/cpus/network/exec_timeout/read_only/memory_swap_mb + hardening) | `sandbox.resources.*` (same fields) |
| `sandbox.agent_scope.*` (the second resource tier) | **removed** — one `sandbox.resources` profile per agent |
| `sandbox.workspace_scope` (and legacy `sandbox.scope`) | `sandbox.workspace_scope` |
| `sandbox.idle_hours` | `sandbox.idle_hours` |
| `sandbox.skill_mount.*` | `sandbox.skill_mount.*` (already per-agent) |

`sandbox.mode` is unchanged by this migration (see the separate
`per-agent-sandbox-enablement` change).

## How to migrate

For each agent that should keep the old shared behavior, copy the values from the old
`platform.yaml` `sandbox:` section into that agent's `agent.yaml`:

```yaml
# agent.yaml
sandbox:
  workspace_scope: session      # was platform.yaml sandbox.workspace_scope / scope
  idle_hours: 2.0               # was platform.yaml sandbox.idle_hours
  resources:                    # was platform.yaml sandbox.resources
    memory: 256
    cpus: 0.5
    network: none               # none | public_only | allow_all
    exec_timeout: 30
    read_only: true
    # hardening (optional; safe defaults apply when omitted):
    # pids_limit: 256
    # tmpfs_size_mb: 64
    # cap_drop_all: true
    # cap_add: []
    # no_new_privileges: true
    # init: true
    # run_as_user: "65534:65534"
```

Notes:

- **Unset fields inherit the same safe code defaults** as before — you only need to
  declare what you want to override.
- **`agent_scope` is gone.** Previously the `agent` workspace-scope tier could override
  memory/cpus/network via `sandbox.agent_scope`. Each agent now has a single
  `sandbox.resources` profile that applies regardless of `workspace_scope` (which still
  controls data-isolation granularity only). If you relied on different resources for
  agent- vs session-scoped containers within one agent, pick the single profile you want.
- **Remove the migrated keys from `platform.yaml`.** They are no longer read; leaving
  them has no effect (no deprecation warning is emitted).
- A direct `fleetent agent run` process with no `platform.yaml` now resolves its full sandbox resource
  profile from `agent.yaml` + code defaults.

## Code-execution enablement (`sandbox.mode` removed)

The global tri-state `sandbox.mode` (`off` / `selective` / `all`) is removed
(`per-agent-sandbox-enablement`). Code-execution enablement is now decided per agent by
`features.code_execution` (unset/`true` = on, `false` = off), gated by runtime backend
availability (no Docker → off for everyone). Remove `sandbox.mode` from `platform.yaml`
and translate it:

| Old `platform.yaml` `sandbox.mode` | New per-agent `agent.yaml` |
|---|---|
| `all` (default) | leave `features.code_execution` unset (on) on agents that should run code |
| `selective` | set `features.code_execution: true` only on authorized agents; others unset/`false` |
| `off` (host kill-switch) | set `features.code_execution: false` on every agent that must not run code |

Notes:

- The "no Docker → off" runtime degrade is unchanged and still applies regardless of config.
- The medium auto-approval coupling (`action_gate_medium_mode: sandbox`) now keys on the
  runtime `sandbox_capable` signal (backend available **and** the agent has code execution
  enabled); when not capable, those medium operations fail closed and page approval.
