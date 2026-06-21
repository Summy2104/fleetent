# install-platform-script Specification

## Purpose
专为 platform 控制面设计的安装脚本。安装 binary、建 platform DB（alembic）、
初始化 admin 用户，不涉及 agent 配置。

## Requirements

### Requirement: install-platform.sh deploys the platform control plane

`scripts/install-platform.sh` SHALL install fleetent, run `alembic upgrade head` on
`$FLEETENT_HOME/data/fleetent.db`, seed the built-in admin, and build the admin SPA
(`make frontend-install && make frontend-build`) so the deployed platform can serve
`/admin/ui`. If node/yarn is unavailable, the script SHALL install it (or fail with a
clear, actionable message) rather than silently skip the build. It SHALL NOT create any
agent home directories.

#### Scenario: install-platform.sh creates platform DB

- **WHEN** `scripts/install-platform.sh` is called in a fleetent repo directory
- **THEN** `$FLEETENT_HOME/data/fleetent.db` SHALL exist with platform tables
- **AND** no agent home directory SHALL be created under `$FLEETENT_HOME/agents/`

#### Scenario: install builds the admin SPA

- **WHEN** `scripts/install-platform.sh` completes successfully
- **THEN** `frontend/dist` SHALL exist (built admin SPA), so the platform serves `/admin/ui` instead of a 503

#### Scenario: missing node tooling is explicit

- **WHEN** node/yarn is not available on the install host
- **THEN** the script installs it or aborts with a clear message and remediation, and SHALL NOT leave the platform with an unbuilt frontend silently
