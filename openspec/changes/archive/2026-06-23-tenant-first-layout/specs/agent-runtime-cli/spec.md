## MODIFIED Requirements

### Requirement: Standalone agent runtime via `fleetent agent run`

`fleetent agent run <agent-id> [--port N]` SHALL boot a single agent home as a foreground process (loop + bound IM + optional HTTP/ws): by default it resolves `FLEETENT_HOME/tenants/default/agents/<agent-id>/` for standalone/dev compatibility, while managed node invocations SHALL pass the tenant-aware home explicitly. The command loads `agent.yaml` + `.env` + `data/`, runs the agent loop, and brings up that agent's IM connectors. **该命令是 node 拉起 agent 的原语**, 也可被开发者直接运行作 dev/test 调试。

#### Scenario: Standalone default tenant run
- **WHEN** developer runs `fleetent agent run support` without `--home`
- **THEN** runtime loads `FLEETENT_HOME/tenants/default/agents/support/agent.yaml`
- **AND** uses `FLEETENT_HOME/tenants/default/agents/support/data/` for runtime data

#### Scenario: Node passes explicit tenant-aware home
- **WHEN** node starts tenant `acme` agent `support`
- **THEN** it invokes the agent runtime with explicit home `FLEETENT_HOME/tenants/acme/agents/support`
- **AND** runtime does not infer the wrong default tenant home

#### Scenario: Explicit home wins
- **WHEN** `fleetent agent run support --home /tmp/custom-home` is used
- **THEN** runtime loads `/tmp/custom-home/agent.yaml`
- **AND** all agent data redirects under `/tmp/custom-home/data`

### Requirement: Scaffold an agent home via `fleetent agent init`

`fleetent agent init <agent-id>` SHALL create `FLEETENT_HOME/tenants/default/agents/<agent-id>/` from a built-in template, with zero platform/DB dependency.

#### Scenario: Init writes default tenant home
- **WHEN** developer runs `fleetent agent init solo`
- **THEN** `FLEETENT_HOME/tenants/default/agents/solo/agent.yaml` exists
- **AND** `.env`, `skills/`, and `data/` are initialized as standalone runtime inputs
