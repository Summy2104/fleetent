## 1. scripts/install-agent.sh — 新建

- [x] 1.1 Write `scripts/install-agent.sh`: requires agent-id arg; installs uv + fleetent (`--from .`); persists FLEETENT_HOME; runs `fleetent agent init <agent-id>`; checks Docker
- [x] 1.2 Make executable: `chmod +x scripts/install-agent.sh`

## 2. scripts/install-platform.sh — 新建

- [x] 2.1 Write `scripts/install-platform.sh`: installs uv + fleetent (`--from .`); persists FLEETENT_HOME; copies `.env.example` + `platform.yaml.example`; runs `alembic upgrade head`; runs `fleetent-admin seed-builtin-admin`
- [x] 2.2 Make executable: `chmod +x scripts/install-platform.sh`

## 3. scripts/install.sh — 重构

- [x] 3.1 Refactor `scripts/install.sh` to call `install-agent.sh` + `install-platform.sh`; add `--agent-only`, `--platform-only`, `--agent-id` flags; keep `--editable` for dev mode; remove `copy_config_templates` and `init_db` inline functions

## 4. 文档更新

- [x] 4.1 Update `docs/local/my-bot-deployment.md` to reference `scripts/install-agent.sh my-bot`

## 5. 验证

- [x] 5.1 Run `bash -n scripts/install-agent.sh && bash -n scripts/install-platform.sh && bash -n scripts/install.sh` (syntax check, no execution)
