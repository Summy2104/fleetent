# deployment-docker-compose-foundation

## Why

当前 Pilot 部署文档仍然要求 operator 先理解源码、`uv`、配置文件、migration 脚本和服务启动命令，再把这些步骤手动串起来。仓库已有 `Dockerfile` 和 `docker-compose.yml`，但它们还不是完整的 Pilot 默认部署入口：

- Docker image 没有复制 `scripts/`，容器内无法稳定执行 upgrade / 初始化类脚本。
- Compose 依赖 `.env.production`，但项目决策是只提交 `.env.example`，初始化后生成本地 `.env`。
- 没有 `fleetent admin init-config`，operator 需要手动复制 `config/*.example`。
- migration 和服务启动的推荐顺序没有通过 compose 流程表达。
- 文档端口、部署入口和旧配置文件边界不一致。
- `secrets/` 目录和 `credential_ref` 文件路径没有简单、统一、可解释的约定。

这导致 `pilot-runbook.md` 即使补充场景，也仍然不够好用：部署能力本身缺少一个清晰、可重复的入口。

## What Changes

- 将 Docker Compose 定义为 Pilot 默认部署入口；`uv run uvicorn` 保留为开发模式。
- 补齐 Dockerfile / compose，使容器内可执行 `fleetent`、`fleetent-admin` 和 `scripts/upgrade.py`。
- 新增 `fleetent admin init-config`，用于生成本地 `.env`、`config/settings.yaml`、`config/mcp.servers.yaml`，并创建 `data/`、`data/logs/`、`data/diagnostics/` 和平铺 `secrets/` 目录。
- 只提交 `.env.example`；本地 `.env` 不进 git。
- `secrets/` 不进 git，目录平铺，只保存不分 scope 的部署级 secret 文件，例如 `google-drive-token.json`、`confluence-api-token`。
- Compose 挂载 `./data:/app/data`、`./config:/app/config`、`./secrets:/app/secrets:ro`，端口统一 `8765`。
- migration 支持两种模式：
  - Pilot / production 推荐显式执行：`docker compose run --rm fleetent uv run python scripts/upgrade.py`。
  - 开发便捷模式可选 `FLEETENT_AUTO_UPGRADE=true`，entrypoint 启动服务前自动运行 upgrade，默认关闭。
- 清理 tracked `config/mcp.yaml`，保留 `config/mcp.servers.yaml.example`，并确保旧配置文件仍按现有配置 spec fail fast。
- 更新 deployment docs / runbook，使 Docker Compose 成为默认 Pilot 部署流程。

## 模块边界影响

- owning package：`deployment` / `configuration`；代码主要落在 `platform.admin_cli`、`scripts/` 和根部署文件。
- public API surface：
  - 新增 operator CLI：`fleetent-admin init-config [--dry-run] [--force]`。
  - 新增 container entrypoint：`scripts/docker_entrypoint.sh` 或等价 Python/shell entrypoint。
- owned tables：无新增。
- config namespace：无新增 runtime namespace；新增部署环境变量 `FLEETENT_AUTO_UPGRADE`，并新增 `.env.example`。
- cross-module dependencies：
  - `init-config` 复用 configuration examples，不读取或生成真实 secret。
  - entrypoint 调用既有 `scripts/upgrade.py` 和 `uvicorn fleetent.server:app`。
  - docs 引用 observability、KB connector 和 diagnostics CLI，但不改变这些模块。
- migration / shim plan：
  - 删除 tracked legacy `config/mcp.yaml`。
  - 不保留 `.env.production` 兼容；compose 改为 `.env`。
  - 不新增旧部署命令 shim；`uv run uvicorn` 作为开发模式保留在文档中。

## 非目标

- 不做 Kubernetes、Helm、systemd、TLS、镜像发布流水线或自动 release。
- 不做企业 secret manager 集成。
- 不做 scope 级 credential 管理；connector scope 仍由 settings 或未来数据库 connector 配置表达。
- 不自动生成任何真实 secret 文件。
- 不把 migration 默认绑定到生产服务启动；auto-upgrade 仅显式 opt-in。
