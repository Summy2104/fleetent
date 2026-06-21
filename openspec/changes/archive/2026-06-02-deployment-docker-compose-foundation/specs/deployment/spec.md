## ADDED Requirements

### Requirement: Docker Compose Pilot deployment entrypoint
部署 SHALL 提供 Docker Compose 作为 Pilot 默认部署入口，同时保留源码 `uv run uvicorn` 作为开发模式。

#### Scenario: Compose service is the documented Pilot default
- **WHEN** operator 阅读 Pilot 部署文档或 runbook
- **THEN** 文档优先使用 `docker compose` 流程启动 fleetent
- **AND** 源码 `uv run uvicorn fleetent.server:app` 只标注为开发模式

#### Scenario: Compose exposes the standard Pilot port
- **WHEN** operator 使用 docker compose 启动 fleetent
- **THEN** 服务通过 `http://127.0.0.1:8765/health` 做 health check
- **AND** 文档中的 Pilot 默认端口为 `8765`

#### Scenario: Compose mounts deployment state directories
- **WHEN** operator 查看 `docker-compose.yml`
- **THEN** compose 挂载 `./data:/app/data`
- **AND** 挂载 `./config:/app/config`
- **AND** 挂载 `./secrets:/app/secrets:ro`

#### Scenario: Compose uses local env file
- **WHEN** operator 查看 `docker-compose.yml`
- **THEN** compose 使用 `.env`
- **AND** 不引用 `.env.production`

### Requirement: Container image includes deployment tooling
Docker image SHALL include enough project files to run the service, admin CLI and SQLite upgrade script inside the container.

#### Scenario: Container includes runtime and migration assets
- **WHEN** Docker image is built
- **THEN** image contains `src/`, `migrations/`, `scripts/`, `alembic.ini`, `pyproject.toml` and `uv.lock`

#### Scenario: Container can run operator commands
- **WHEN** operator enters the fleetent container or uses `docker compose run --rm fleetent`
- **THEN** `uv run fleetent --help` works
- **AND** `uv run fleetent admin --help` works
- **AND** `uv run python scripts/upgrade.py --dry-run` works

### Requirement: Explicit migration is recommended for Pilot
Pilot deployment docs SHALL recommend explicit migration before service startup, while allowing optional auto-upgrade only by explicit opt-in.

#### Scenario: Pilot migration is explicit
- **WHEN** operator follows Pilot deployment runbook
- **THEN** operator runs `docker compose run --rm fleetent uv run python scripts/upgrade.py`
- **AND** only after successful upgrade runs `docker compose up -d`

#### Scenario: Auto-upgrade is disabled by default
- **WHEN** `FLEETENT_AUTO_UPGRADE` is unset or false
- **THEN** container startup does not run `scripts/upgrade.py`

#### Scenario: Auto-upgrade is opt-in
- **WHEN** `FLEETENT_AUTO_UPGRADE=true`
- **THEN** container entrypoint runs `uv run python scripts/upgrade.py` before starting uvicorn
- **AND** startup fails if upgrade fails

### Requirement: Docker deployment docs cover secrets and init flow
Deployment docs SHALL explain the Docker Compose first Pilot flow, local env file, flat secrets directory and config initialization.

#### Scenario: Init flow is documented
- **WHEN** operator reads deployment docs
- **THEN** docs instruct operator to run `fleetent admin init-config`
- **AND** docs explain which files and directories are created

#### Scenario: Flat secrets directory is documented
- **WHEN** operator reads deployment docs
- **THEN** docs state `secrets/` is a flat deployment-level directory
- **AND** docs give examples such as `google-drive-token.json` and `confluence-api-token`
- **AND** docs state file names do not express connector scope

#### Scenario: Secret files are excluded from reports
- **WHEN** operator prepares diagnostics or issue evidence
- **THEN** docs prohibit including files from `secrets/`
- **AND** docs require using credential references rather than credential payloads
