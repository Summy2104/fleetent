## MODIFIED Requirements

### Requirement: Standalone agent runtime via `fleetent agent run`

The `fleetent` command SHALL provide `agent run <agent-id> [--port N]` that boots a
single agent as a self-contained foreground process: it resolves the agent home at
`FLEETENT_HOME/<agent-id>/` (`agent.yaml` + `.env` + `data/` + local access), loads it,
runs the agent loop, and starts that agent's IM connectors. The process SHALL run
without any platform service.

Before scanning `agent.yaml`, `boot()` SHALL load `<home_dir>/.env` into the process
`os.environ` using `load_dotenv(override=False)`. If the file does not exist the step
SHALL be silently skipped. Variables already present in the process environment (injected
by systemd `EnvironmentFile`, Docker `--env-file`, or shell `export`) SHALL take
precedence over values in `.env`.

#### Scenario: Boot one agent from its home

- **WHEN** `fleetent agent run support` is invoked and `FLEETENT_HOME/support/agent.yaml`
  exists
- **THEN** the process loads that home's agent and starts its IM connectors, with no
  platform server required

#### Scenario: IM is always bound to the agent

- **WHEN** the agent home declares `connectors.slack`
- **THEN** the running agent process maintains that Slack connection; IM is not available
  outside an agent process

#### Scenario: .env is loaded before agent.yaml is scanned

- **WHEN** `<home_dir>/.env` exists and contains `SLACK_BOT_TOKEN=xoxb-abc`
- **THEN** `os.environ["SLACK_BOT_TOKEN"]` equals `xoxb-abc` by the time `scan_home()` runs
- **AND** downstream consumers (`slack_supervisor`, `model/resolver`) read the correct value

#### Scenario: Missing .env is silently skipped

- **WHEN** `<home_dir>/.env` does not exist
- **THEN** `boot()` proceeds normally without error
- **AND** agent startup behaviour is identical to the pre-change state

#### Scenario: Process-level env takes precedence over .env

- **WHEN** `SLACK_BOT_TOKEN=xoxb-injected` is already set in the process environment
- **AND** `<home_dir>/.env` contains `SLACK_BOT_TOKEN=xoxb-from-file`
- **THEN** `os.environ["SLACK_BOT_TOKEN"]` remains `xoxb-injected`
- **AND** the `.env` value is NOT applied

#### Scenario: Multiple agents on the same server have isolated environments

- **WHEN** two `fleetent agent run` processes start concurrently for `agent-a` and `agent-b`
- **AND** each home contains a `.env` with the same variable name but different values
- **THEN** the `agent-a` process sees only `agent-a`'s value
- **AND** the `agent-b` process sees only `agent-b`'s value
- **AND** neither process's `os.environ` is visible to the other
