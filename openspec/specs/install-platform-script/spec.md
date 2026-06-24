# install-platform-script Specification

## Purpose
专为 platform 控制面设计的安装脚本。安装 binary、建 platform DB（alembic）、
初始化 admin 用户，不涉及 agent 配置。

## Requirements

### Requirement: install-platform.sh deploys the platform control plane

`scripts/install-platform.sh` SHALL install fleetent, run Platform DB migrations on
`$FLEETENT_HOME/management.db`, seed the built-in admin via `fleetent platform
seed-builtin-admin`, and build the admin SPA (`make frontend-install && make
frontend-build`) so the deployed platform can serve `/admin/ui`. If node/yarn is
unavailable, the script SHALL install it (or fail with a clear, actionable message)
rather than silently skip the build. It SHALL NOT create any agent home directories.
The post-install start instruction SHALL use `fleetent platform serve`, not a bare
uvicorn command.

#### Scenario: install-platform.sh creates platform DB

- **WHEN** `scripts/install-platform.sh` is called in a fleetent repo directory
- **THEN** `$FLEETENT_HOME/management.db` SHALL exist with platform tables
- **AND** no agent home directory SHALL be created under `$FLEETENT_HOME/tenants/`

#### Scenario: install builds the admin SPA

- **WHEN** `scripts/install-platform.sh` completes successfully
- **THEN** `frontend/dist` SHALL exist (built admin SPA), so the platform serves `/admin/ui` instead of a 503

#### Scenario: missing node tooling is explicit

- **WHEN** node/yarn is not available on the install host
- **THEN** the script installs it or aborts with a clear message and remediation, and SHALL NOT leave the platform with an unbuilt frontend silently

#### Scenario: install prints platform serve command

- **WHEN** `scripts/install-platform.sh` completes successfully
- **THEN** next steps mention `fleetent platform serve`
- **AND** next steps do not use bare `uvicorn fleetent.server:app`
