# Design

## 设计目标

Pilot 部署需要一个默认、可重复、可解释的入口。这个入口应让 operator 能按固定顺序完成：

1. 初始化本地配置和目录。
2. 填写 `.env` 和 secret 文件。
3. 显式运行 backup / migration。
4. 启动服务。
5. 通过 health check、admin CLI 和 runbook 验收。

因此本 change 把 Docker Compose 作为 Pilot 默认入口，而不是继续依赖源码环境下的 `uv run uvicorn`。

## 部署模式

### Pilot 默认模式

```bash
docker compose run --rm fleetent uv run fleetent-admin init-config
docker compose run --rm fleetent uv run python scripts/upgrade.py
docker compose up -d
curl -fsS http://127.0.0.1:8765/health
```

特点：

- migration 是显式步骤，operator 能看到 backup 路径、migration 结果和失败恢复提示。
- 服务启动不偷偷修改 SQLite schema。
- `data/`、`config/`、`secrets/` 都是宿主机目录，便于备份、检查和迁移。

### 开发便捷模式

```bash
FLEETENT_AUTO_UPGRADE=true docker compose up
```

特点：

- 默认关闭。
- 只在显式设置 `FLEETENT_AUTO_UPGRADE=true` 时，entrypoint 启动服务前运行 `scripts/upgrade.py`。
- 适合临时开发 / demo，不作为 Pilot 推荐流程。

## Dockerfile

Docker image 应包含：

- `src/`
- `migrations/`
- `scripts/`
- `config/*.example`
- `alembic.ini`
- `pyproject.toml` / `uv.lock`

容器内必须能执行：

```bash
uv run fleetent --help
uv run fleetent-admin --help
uv run python scripts/upgrade.py --dry-run
```

Dockerfile 继续使用 Python 3.12 slim 和 `uv sync --no-dev --frozen`。端口统一暴露 `8765`。

## Docker Compose

Compose 服务名继续为 `fleetent`。

挂载：

```yaml
volumes:
  - ./data:/app/data
  - ./config:/app/config
  - ./secrets:/app/secrets:ro
```

环境：

- `env_file: .env`
- 不再使用 `.env.production`

端口：

```yaml
ports:
  - "8765:8765"
```

`host.docker.internal` 保留，用于容器访问宿主机模型服务、embedding endpoint 或 MCP / sandbox 依赖。

## 配置初始化

新增 operator 命令：

```bash
uv run fleetent-admin init-config
uv run fleetent-admin init-config --dry-run
uv run fleetent-admin init-config --force
```

行为：

- 从 `.env.example` 生成 `.env`。
- 从 `config/settings.yaml.example` 生成 `config/settings.yaml`。
- 从 `config/mcp.servers.yaml.example` 生成 `config/mcp.servers.yaml`。
- 创建 `data/`、`data/logs/`、`data/diagnostics/` 和 `secrets/`。
- 默认不覆盖已有文件。
- `--dry-run` 只输出将创建 / 跳过 / 覆盖的路径，不写文件系统。
- `--force` 覆盖已存在的 generated files，但不删除未知文件、不生成真实 secret。

输出必须告诉 operator：

- 哪些文件已创建。
- 哪些文件已存在并被跳过。
- 下一步应该编辑 `.env` 和 `config/settings.yaml`，并把真实 secret 文件放入 `secrets/`。

## `.env` 策略

版本控制只提交 `.env.example`。

初始化生成本地 `.env`。不区分 `.env.production`，避免 Pilot 文档继续分叉。

`.env.example` 只包含空值或安全默认值，例如：

```env
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
FLEETENT_CONFLUENCE_API_TOKEN=
FLEETENT_AUTO_UPGRADE=false
```

真实 secret 不进入 git、docs、trace、logs、diagnostics package 或 issue。

## `secrets/` 策略

`secrets/` 是部署级本地 secret 文件目录：

```text
secrets/
  google-drive-token.json
  confluence-api-token
  github-mcp-api-key
```

约束：

- 目录平铺。
- 文件名不表达 scope。
- 文件只表达部署级 credential。
- connector scope 由 `settings.yaml` 或未来数据库 connector 配置表达，不靠文件路径表达。
- `secrets/` 不进 git。
- `init-config` 创建空 `secrets/` 目录，但不生成任何 secret 文件。
- 提交 `secrets.example.md` 或 `docs/deployment/secrets.md` 说明示例文件名和边界。

示例 credential ref：

```yaml
credential_ref: "file:///app/secrets/google-drive-token.json"
```

## Entry Point

推荐新增 `scripts/docker_entrypoint.sh`：

```bash
#!/usr/bin/env bash
set -euo pipefail

if [ "${FLEETENT_AUTO_UPGRADE:-false}" = "true" ]; then
  uv run python scripts/upgrade.py
fi

exec uv run uvicorn fleetent.server:app --host 0.0.0.0 --port 8765
```

entrypoint 不自动 init-config。原因：

- 配置初始化可能需要 operator 编辑 `.env` 和 secret。
- 服务启动时自动生成配置会掩盖部署错误。

## 文档调整

需要更新：

- `docs/deployment/pilot-install-checklist.md`
- `docs/deployment/pilot-acceptance-guide.md`
- `docs/deployment/pilot-runbook.md`
- `docs/capabilities/deployment.md`
- `docs/README.md` 如需说明 runbook 与 compose 的入口关系

文档应把 Docker Compose 放在 Pilot 默认路径：

```bash
docker compose run --rm fleetent uv run fleetent-admin init-config
docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run
docker compose run --rm fleetent uv run python scripts/upgrade.py
docker compose up -d
curl -fsS http://127.0.0.1:8765/health
```

`uv run uvicorn fleetent.server:app` 只作为开发模式保留。

## 风险和取舍

- **显式 migration 比自动 migration 麻烦一点**，但 Pilot / production 更安全，backup 和失败恢复可见。
- **保留可选 auto-upgrade** 会增加一个 entrypoint 分支，但默认关闭，不改变生产安全基线。
- **平铺 secrets 比分目录简单**，适合 Pilot。未来如果同一 provider 多 scope credential 增多，应进入 connector credential 管理或企业 secret manager，而不是扩展文件命名语义。
- **不做 Kubernetes / systemd**，避免在 Pilot 阶段扩大交付面。
