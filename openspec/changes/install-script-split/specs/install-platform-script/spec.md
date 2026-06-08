# install-platform-script Specification

## Purpose
专为 platform 控制面设计的安装脚本。安装 binary、建 platform DB（alembic）、
初始化 admin 用户，不涉及 agent 配置。

## Requirements

### Requirement: install-platform.sh deploys the platform control plane

`scripts/install-platform.sh` SHALL install fleetent, run `alembic upgrade head` on
`$FLEETENT_HOME/data/fleetent.db`, and seed the built-in admin. It SHALL NOT create
any agent home directories.

#### Scenario: install-platform.sh creates platform DB

- **WHEN** `scripts/install-platform.sh` is called in a fleetent repo directory
- **THEN** `$FLEETENT_HOME/data/fleetent.db` SHALL exist with platform tables
- **AND** no agent home directory SHALL be created under `$FLEETENT_HOME/agents/`
