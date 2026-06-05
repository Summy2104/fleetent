## Why

两件相关的整理：(1) 部署的 agent home 应当**扁平**——`agent.yaml` 直接在 home 根（`FLEETENT_HOME/agent.yaml`），与 `fleetent agent run <id>` 的 per-agent home（`FLEETENT_HOME/<id>/agent.yaml`）布局一致，而非现在多一层 `config/`。(2) 仓库的配置示例应**按使用方分目录**——`config/agent/`（agent.yaml + 该 agent 的 .env）与 `config/platform/`（平台 .env），且把根目录的 `.env.example` 收进 `config/` 下,让"哪份配置给谁用"一目了然。

## What Changes

- **运行时**：`paths.agent_file()` 由 `config_dir()/agent.yaml` 改为 `base_dir()/agent.yaml`（home 根）。home agent 一次性 `fleetent "<prompt>"` 随之读扁平路径。
- **install.sh**：seed `FLEETENT_HOME/agent.yaml`（从 `config/agent/agent.yaml.example`）+ `FLEETENT_HOME/.env`（从 `config/agent/.env.example`），**不建 `config/` 子目录**。部署 home 扁平：`agent.yaml` + `.env` + `data/`。
- **模板重排**：
  - `config/agent/agent.yaml.example`（← `config/agent.yaml.example`）
  - `config/agent/.env.example`（agent 的 env：LLM keys + 该 agent 的 connector/MCP/KB token + 沙箱/vision/上下文调优）
  - `config/platform/.env.example`（平台 env：`ANTHROPIC_API_KEY`〔Settings 必填，共用〕+ `FLEETENT_AUTO_UPGRADE` + `DATABASE_URL` + TUI + LOG_FORMAT）
  - 删除根 `.env.example` 与 `config/agent.yaml.example`
- **init_config**：`fleetent-admin init-config` 的 `.env` 模板源改为 `config/platform/.env.example`（平台脚手架）。
- **Dockerfile**：COPY 路径更新到新模板位置。
- **.gitignore**：忽略真实 `config/agent/agent.yaml`、`config/agent/.env`、`config/platform/.env`；保留 `*.example` 受版本控制。

## Capabilities

### Modified Capabilities
- `file-agent-runtime`: home agent 单文件加载路径由 `FLEETENT_HOME/config/agent.yaml` 改为 `FLEETENT_HOME/agent.yaml`（扁平 home 根）。
- `install-bootstrap`: install.sh seed 位置由 `FLEETENT_HOME/config/agent.yaml` 改为扁平 `FLEETENT_HOME/agent.yaml`（无 config/ 子目录）。
- `configuration`: 示例模板位置由 `config/agent.yaml.example` 改为 `config/agent/agent.yaml.example`，并按 agent/platform 分目录的 `.env.example`。

## Impact

- **修改**：`paths.py`、`scripts/install.sh`、`admin_cli/init_config.py`、`Dockerfile`、`.gitignore`、模板文件、相关测试（test_paths/test_agent_config/test_deployment_docs/test_admin_init_config/test_install_script/test_run_sync_home_agent）。
- **不变**：`fleetent agent run <id>`（已用扁平 `FLEETENT_HOME/<id>/agent.yaml`）、平台控制面、加载器（仍容忍全局文件缺失）、`agent init`（用 `resolve_home`，不受 `agent_file` 影响）。
- **BREAKING**（部署布局）：已有 `FLEETENT_HOME/config/agent.yaml` 的部署需把 `agent.yaml` 移到 home 根；文档说明。
- **分支**：基于并合回 `main`。
