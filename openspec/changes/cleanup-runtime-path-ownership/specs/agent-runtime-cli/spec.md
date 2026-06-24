## MODIFIED Requirements

### Requirement: Standalone agent runtime via `fleetent agent run`

`fleetent agent run <agent-id> [--port N]` SHALL boot a single agent home as a foreground process (loop + bound IM + optional HTTP/ws): by default it resolves `FLEETENT_HOME/tenants/default/agents/<agent-id>/` for standalone/dev compatibility, while managed node invocations SHALL pass the tenant-aware home explicitly. The command loads `agent.yaml` + `.env` + `data/`, runs the agent loop, and brings up that agent's IM connectors. **该命令是 node 拉起 agent 的原语**, 也可被开发者直接运行作 dev/test 调试。

At boot, before runtime infrastructure can write files, the process SHALL redirect every agent-run data sink to `<home>/data/`: sessions, logs, diagnostics, IM approvals, legacy JSONL traces, workspaces, tool spillover, sandbox output spill, agent-side DBs and vector DBs.

#### Scenario: Standalone default tenant run
- **WHEN** developer runs `fleetent agent run support` without `--home`
- **THEN** runtime loads `FLEETENT_HOME/tenants/default/agents/support/agent.yaml`
- **AND** uses `FLEETENT_HOME/tenants/default/agents/support/data/` for runtime data
- **AND** does not write agent runtime files under `FLEETENT_HOME/data/`

#### Scenario: Node passes explicit tenant-aware home
- **WHEN** node starts tenant `acme` agent `support`
- **THEN** it invokes the agent runtime with explicit home `FLEETENT_HOME/tenants/acme/agents/support`
- **AND** runtime does not infer the wrong default tenant home
- **AND** all data sinks bind under `FLEETENT_HOME/tenants/acme/agents/support/data/`

#### Scenario: Explicit home wins
- **WHEN** `fleetent agent run support --home /tmp/custom-home` is used
- **THEN** runtime loads `/tmp/custom-home/agent.yaml`
- **AND** all agent data redirects under `/tmp/custom-home/data`

### Requirement: Agent runtime legacy trace path is agent-scoped

While the legacy JSONL trace API remains importable, agent runtime SHALL bind its trace file to `<agent-home>/data/traces.jsonl`, not `FLEETENT_HOME/data/traces.jsonl`.

#### Scenario: Agent run writes legacy trace under agent data
- **WHEN** an agent run records a legacy JSONL trace event
- **THEN** the trace is appended to `<agent-home>/data/traces.jsonl`
- **AND** `FLEETENT_HOME/data/traces.jsonl` is not created
