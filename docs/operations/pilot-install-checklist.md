# Pilot MVP 安装清单

本清单是 [pilot-runbook.md](pilot-runbook.md) 的安装阶段参考。第一次测试环境部署和验收时，优先按
runbook 的顺序执行；本清单用于核对安装、升级、备份、回滚和问题上报边界。

## 适用范围

本清单用于 fleetent Pilot MVP 的 on-premises 小范围试用部署。目标是让 operator 能按顺序完成安装、
升级、备份、启动、健康检查、知识库同步、排障、回滚和验收。

非目标：

- 不覆盖完整一键安装包。
- 不覆盖 license key、Admin UI 或 scheduler。
- 不替代企业内部 secret manager、备份系统和变更审批流程。

## 前置条件

- 目标机器能访问企业允许的 LLM / embedding endpoint。
- 目标机器能访问 Pilot 需要的 Google Drive / Confluence scope。
- 已准备 Docker 和 Docker Compose，目标机器可从源码目录构建镜像。
- 已确认服务端口 `8765` 未被占用，运行用户对 `data/`、`config/`、`secrets/` 有读写权限。
- 已确认问题上报渠道和回滚负责人。

## 配置与 Secret 边界

配置文件只保存非敏感设置和 credential reference：

- `agents/<agent-id>/agent.yaml`：保存该 Agent 的 model、MCP servers、knowledge binding、connector scope 等非敏感配置。
- 平台 `.env` 保存平台进程变量；`agents/<agent-id>/.env` 保存该 Agent runtime 所需 secret 值或空占位。
- Google Drive / Confluence credential 使用平铺的 `*_env` 引用，例如
  `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`、`FLEETENT_CONFLUENCE_TOKEN`。
- 真实 secret 文件、环境变量注入方式和权限由部署方管理。

不要把真实 secret、token、credential payload 写入 agent config、日志、trace、diagnostics package、issue 或测试 fixture。
问题上报包不包含真实 secret。

## 安装、升级与备份

Pilot 默认使用 Docker Compose。先初始化本地配置和目录：

```bash
docker compose run --rm fleetent uv run fleetent-admin init-config
```

编辑平台 `.env`、`agents/<agent-id>/agent.yaml`、`agents/<agent-id>/.env`，并把真实 secret 文件放入 `secrets/` 后，升级前先 dry-run：

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run
```

dry-run 通过后执行升级脚本。脚本会在 SQLite backup 成功后运行 `alembic upgrade head`：

> **迁移要求（当前 head）**：`api_keys`、`audit_log`、`im_users` 等管理表已由 Alembic 管理，应用启动前须先完成 `alembic upgrade head`；否则管理 API 会报 "no such table" 错误。

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py
```

只做备份、不迁移：

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py --backup-only
```

验收点：

- dry-run 输出 database URL、backup 路径和 migration 计划。
- 非 dry-run 模式下，SQLite backup 写入 `data/backups/YYYYMMDD-HHMMSS/`，按数据目录结构**镜像全部物理库**（管理库 `management.db` + per-tenant 的 KB / 共享记忆库 + per-agent `agent_state.db` + 各向量库，含 `-wal`/`-shm`）。
- 只有 backup 成功后才运行 `alembic upgrade head`。
- migration 失败时保留 backup，不自动 rollback。

## 启动与健康检查

启动服务：

```bash
docker compose up -d
```

健康检查：

```bash
curl -fsS http://127.0.0.1:8765/health
```

`uv run uvicorn fleetent.server:app` 只作为开发模式保留，不作为 Pilot 默认部署入口。

验收点：

- 服务在 `8765` 端口启动。
- `/health` 返回 200。
- 启动日志不包含 API key、Bearer token、password、secret、token 或 credential payload。
- 启动失败时先查看 structured log 和 diagnostics export，不手写 DB 修改。

## Knowledge Base Connector 验证

查看 connector 配置摘要：

```bash
uv run fleetent-admin kb connectors list
```

检查单个 connector：

```bash
uv run fleetent-admin kb connectors check eng-drive
```

dry-run 同步：

```bash
uv run fleetent-admin kb connectors sync eng-drive --dry-run
```

执行同步：

```bash
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  uv run fleetent-admin kb connectors sync eng-drive --yes --pilot-fixture
```

查看最近一次状态：

```bash
uv run fleetent-admin kb connectors status eng-drive
```

验收点：

- `list` 输出 connector id、type、tenant、KB 和 scope，不输出 credential payload。
- `check` 返回 `ok` 或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、
  `scope_unreachable`。
- `sync --dry-run` 不写 KB、source state 或 vector index。
- `status` 输出最近一次 sync 结果和脱敏失败摘要。

## Observability 查询

查询 run trace：

```bash
uv run fleetent-admin observability traces --run-id run-1 --limit 20
```

查询失败事件：

```bash
uv run fleetent-admin observability traces --event-type agent_run_failed --limit 50
```

查询 usage：

```bash
uv run fleetent-admin observability usage --user-id user-1 --limit 100
```

查询 performance：

```bash
uv run fleetent-admin observability performance --agent-id agent-1 --limit 100
```

验收点：

- `traces` 只输出事件元数据和 payload key summary，不输出 payload 原值。
- `usage` 输出 run count、token usage 和 by-model summary。
- `performance` 输出失败率、延迟、LLM / tool / fallback / permission 指标。

## Diagnostics 与 Retention

导出诊断包：

```bash
uv run fleetent-admin diagnostics export
```

按时间导出诊断包：

```bash
uv run fleetent-admin diagnostics export --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
```

retention dry-run：

```bash
uv run fleetent-admin diagnostics retention dry-run
```

retention apply：

```bash
uv run fleetent-admin diagnostics retention apply
```

验收点：

- diagnostics package 默认写入 `data/diagnostics`。
- diagnostics package 不包含 memory 内容、KB 文档正文 / chunks、SQLite 主库、SQLite backups 或 connector
  credential 文件内容。
- 默认 `diagnostics.retention.enabled=false`，`apply` 应拒绝删除。
- retention 只处理 logs、traces 和 diagnostics export 包，不删除业务数据或 SQLite backups。

## 回滚

如果 migration、启动或 Pilot smoke 失败：

1. 停止 fleetent 服务。
2. 确认最近一次备份批次目录，例如 `data/backups/YYYYMMDD-HHMMSS/`。
3. 用**同一备份批次**按镜像结构把全部库复制回 `data/` 对应位置（如 `…/management.db` → `data/management.db`，及 `<tenant>/`、`<tenant>/<agent_id>/` 子目录下各库），替换当前 DB 文件，保证多库一致、不混用不同时间点的备份。
4. 重启 fleetent 服务。
5. 再次运行 `GET /health`。
6. 运行 `uv run fleetent-admin observability traces --event-type agent_run_failed --limit 20` 查看回滚后是否仍有失败事件。

回滚不自动删除 diagnostics package 和 logs；保留它们用于问题上报。

## 分布式部署（可选：platform 与 agent node 分机）

单机部署（默认）下，platform 进程内置 agent controller，无需额外配置。
若需 platform 与 agent host 分机运行，执行以下额外步骤：

**在 agent host 上**
1. 将代码仓库 clone 到 agent host
2. 运行 `bash scripts/install-agent.sh <agent-id>` 安装 agent node 依赖并初始化 agent home
3. 在 platform 侧注册该 node：`uv run fleetent-admin node register --host <agent-host> --port <port>`

**验证**
- `uv run fleetent-admin node list` — 应显示已注册的 node 及其心跳状态
- `uv run fleetent-admin node deregister <node-id>` — 如需下线

**当前限制**
- node 与 platform 须能互相访问（HTTP）
- agent 运行数据仍落各自 agent host 的本地 SQLite

## Pilot 验收清单

- [ ] Docker Compose 镜像构建完成，`fleetent-admin init-config` 成功。
- [ ] `scripts/upgrade.py --dry-run` 成功。
- [ ] SQLite backup 已创建。
- [ ] 服务启动成功，`GET /health` 返回 200。
- [ ] 默认 agent 可响应一次测试消息。
- [ ] agent 到 KB 绑定符合 Pilot scope。
- [ ] Google Drive / Confluence connector `check` 通过或失败原因明确。
- [ ] KB connector `sync --dry-run` 通过。
- [ ] KB connector `sync` 完成并可查询 `status`。
- [ ] `fleetent-admin observability traces` 可查询测试 run。
- [ ] `fleetent-admin observability usage` 可查询 usage summary。
- [ ] `fleetent-admin observability performance` 可查询 performance summary。
- [ ] `fleetent-admin diagnostics export` 可生成脱敏诊断包。
- [ ] `fleetent-admin diagnostics retention dry-run` 可输出候选数量。
- [ ] 回滚负责人和问题上报路径已确认。

## 问题上报包

问题上报包应包含：

- fleetent 版本、commit SHA 和部署时间。
- `scripts/upgrade.py --dry-run` 输出摘要。
- `GET /health` 结果。
- connector `check` / `status` 的脱敏输出。
- observability `traces` / `usage` / `performance` 的脱敏输出。
- diagnostics export 生成的本地包路径。
- 回滚是否执行、使用的 SQLite backup 路径和回滚后 health check 结果。

问题上报包不包含真实 secret、token、credential payload、用户完整 prompt / reply、KB 文档正文、SQLite 主库或 SQLite backups。
