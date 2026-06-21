## MODIFIED Requirements

### Requirement: install-agent.sh deploys a standalone agent without platform dependencies

`scripts/install-agent.sh [--dir PATH]` SHALL install the fleetent binary, set and persist `FLEETENT_HOME`, run the optional-dependency precheck (warn when Docker is absent), and then print a tutorial guiding the operator to create an agent themselves. It SHALL NOT run `fleetent agent init`, SHALL NOT produce an agent home, SHALL NOT require an `agent-id` argument (no positional argument; only `--dir`), and SHALL NOT run alembic migrations or require `fleetent admin`. The script SHALL be idempotent / re-runnable.

#### Scenario: Install without agent-id installs runtime and prints the create-agent tutorial
- **WHEN** `scripts/install-agent.sh` is called (no positional argument) in a fleetent repo directory
- **THEN** the `fleetent` binary SHALL be installed and `FLEETENT_HOME` set/persisted
- **AND** the script SHALL exit zero and print a tutorial that includes `fleetent agent init <agent-id>`, editing `agent.yaml` + `.env`, and `fleetent agent run <agent-id>`
- **AND** no `$FLEETENT_HOME/agents/<id>/` home SHALL be created by the script
- **AND** no alembic commands SHALL have been executed

#### Scenario: A positional agent-id argument is rejected
- **WHEN** `scripts/install-agent.sh some-id` is called with a positional argument
- **THEN** the script SHALL exit non-zero and print a usage message stating the agent-id argument was removed (create the agent with `fleetent agent init`)

#### Scenario: Tutorial names the agent-creation steps
- **WHEN** the install completes
- **THEN** the printed tutorial SHALL name, in order, `fleetent agent init <agent-id>`, editing `agent.yaml`/`.env`, `fleetent agent run <agent-id> [--port N]`, and connecting via `fleetent tui`
