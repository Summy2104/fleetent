# install-agent-script Specification

## Purpose
专为 standalone agent 设计的安装脚本。安装 fleetent binary、设置 FLEETENT_HOME、
初始化 agent home——无 alembic、无 platform 依赖。

## Requirements

### Requirement: install-agent.sh deploys a standalone agent without platform dependencies

`scripts/install-agent.sh <agent-id>` SHALL install the fleetent binary, set FLEETENT_HOME,
run `fleetent agent init <agent-id>`, and produce a runnable agent home. It SHALL NOT run
alembic migrations or require `fleetent-admin`.

#### Scenario: Missing agent-id exits with usage message

- **WHEN** `scripts/install-agent.sh` is called without an agent-id argument
- **THEN** the script SHALL exit non-zero and print a usage message

#### Scenario: Successful install produces agent home

- **WHEN** `scripts/install-agent.sh my-bot` is called in a fleetent repo directory
- **THEN** `$FLEETENT_HOME/agents/my-bot/agent.yaml` SHALL exist
- **AND** `$FLEETENT_HOME/agents/my-bot/.env` SHALL contain `FLEETENT_TUI_TOKEN`
- **AND** no alembic commands SHALL have been executed
