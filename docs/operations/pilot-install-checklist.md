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
docker compose run --rm fleetent uv run fleetent platform init-config
```

编辑平台 `.env`、`agents/<agent-id>/agent.yaml`、`agents/<agent-id>/.env`，并把真实 secret 文件放入 `secrets/` 后，升级前先 dry-run：

```bash
docker compose run --rm fleetent uv run fleetent platform upgrade --dry-run
```

dry-run 通过后执行升级。升级命令会在 SQLite backup 成功后运行 `alembic upgrade head`：

> **迁移要求（当前 head）**：`api_keys`、`audit_log`、`im_users` 等管理表已由 Alembic 管理，应用启动前须先完成 `alembic upgrade head`；否则管理 API 会报 "no such table" 错误。

```bash
docker compose run --rm fleetent uv run fleetent platform upgrade
```

只做备份、不迁移：

```bash
docker compose run --rm fleetent uv run fleetent platform upgrade --backup-only
```

验收点：

- dry-run 输出 database URL、backup 路径和 migration 计划。
- 非 dry-run 模式下，SQLite backup 写入 `data/backups/YYYYMMDD-HHMMSS/`，按数据目录结构**镜像全部物理库**（管理库 `management.db` + per-tenant 的 KB 库 + per-agent `agent_state.db`〔含 agent memory〕 + 各向量库，含 `-wal`/`-shm`）。
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

`fleetent platform serve` 是主要服务启动入口；`uvicorn fleetent.server:app` 可直接作为 ASGI 应用访问，仅用于开发模式。

验收点：

- 服务在 `8765` 端口启动。
- `/health` 返回 200。
- 启动日志不包含 API key、Bearer token、password、secret、token 或 credential payload。
- 启动失败时先查看 structured log 和 diagnostics export，不手写 DB 修改。

## Knowledge Base Connector 验证

> 平台托管 KB ingest 已退役。`/admin/kb/connectors*`、`/admin/kb/{kb_id}/sync` 和 platform import / extraction 端点不再作为生产入口。
> 升级前请把历史 platform connector 配置誊到 `$FLEETENT_HOME/kb-service/default/kb-service.yaml`，
> 并用 `kb-worker --config $FLEETENT_HOME/kb-service/default/kb-service.yaml` 运行 standalone 队列。

查看 connector 配置摘要：

```bash
GET /admin/kb/connectors
```

检查单个 connector：

```bash
POST /admin/kb/connectors/eng-drive/check
```

dry-run 同步：

```bash
POST /admin/kb/connectors/eng-drive/sync  # body: {"dry_run": true}
```

执行同步：

```bash
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  POST /admin/kb/connectors/eng-drive/sync  # body: {"dry_run": false}
```

查看最近一次状态：

```bash
GET /admin/kb/connectors/eng-drive/status
```

验收点：

- `list` 输出 connector id、type、tenant、KB 和 scope，不输出 credential payload。
- `check` 返回 `ok` 或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、
  `scope_unreachable`。
- `sync --dry-run` 不写 KB、source state 或 vector index。
- `status` 输出最近一次 sync 结果和脱敏失败摘要。

## Observability 查询

查询 agent overview：

```bash
GET /admin/stats/agents/<agent_id>/overview
```

查询 tool 聚合：

```bash
GET /admin/stats/agents/<agent_id>/tools
```

查询 session trace drill-down：

```bash
GET /admin/stats/sessions/<session_id>/trace
```

验收点：

- overview 输出 usage、approvals、cost 聚合，不输出 payload 原值。
- tools 输出按工具聚合的调用与错误概览。
- session trace drill-down 用于定位单次会话内的事件链路。

## Diagnostics 与 Retention

导出诊断包：

```bash
uv run fleetent platform diagnostics export
```

按时间导出诊断包：

```bash
uv run fleetent platform diagnostics export --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
```

retention dry-run：

```bash
uv run fleetent platform diagnostics retention dry-run
```

retention apply：

```bash
uv run fleetent platform diagnostics retention apply
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
3. 用**同一备份批次**按镜像结构把全部库复制回各自位置（如 `…/management.db` → `<FLEETENT_HOME>/management.db`，及 `tenants/<tenant>/agents/<agent>/data/` 下各库），替换当前 DB 文件，保证多库一致、不混用不同时间点的备份。
4. 重启 fleetent 服务。
5. 再次运行 `GET /health`。
6. 运行 `GET /admin/stats/agents/<agent_id>/overview` 与 `GET /admin/stats/sessions/<session_id>/trace`，确认回滚后统计与 trace 查询恢复可用。

回滚不自动删除 diagnostics package 和 logs；保留它们用于问题上报。

## 分布式部署（可选：platform 与 agent node 分机）

单机部署（默认）下，platform 进程内置 agent controller，无需额外配置。
若需 platform 与 agent host 分机运行，执行以下额外步骤：

**在 agent host 上**
1. 将代码仓库 clone 到 agent host
2. 运行 `bash scripts/install-agent.sh` 安装 agent 运行时（不再带 agent-id），再 `fleetent agent init <agent-id>` 创建 agent home
3. 在 platform 侧注册该 node：`uv run fleetent platform node register --host <agent-host> --port <port>`

**验证**
- `uv run fleetent platform nodes list` — 应显示已注册的 node 及其心跳状态和 desired/actual agent 数
- `uv run fleetent platform nodes show <node-id>` — 查看 desired_agents 与 actual_agents 是否收敛
- `uv run fleetent platform nodes reconcile <node-id>` — 手动触发 reconcile（如自动 reconcile 延迟）
- `uv run fleetent platform nodes deregister <node-id>` — 如需下线

**Node supervisor 与 agent placement 验证**
- desired-state 配置中列出需要运行的 agent：platform 侧设置 `desired_agents` 列表
- node supervisor 自动拉起 / 维护 agent 进程，无需手动 `fleetent agent run`
- IM 连接（Slack / Telegram）由 node IM-edge supervisor 建立，不在 agent 进程内直接连接

**当前限制**
- node 与 platform 须能互相访问（HTTP）
- agent 运行数据仍落各自 agent host 的本地 SQLite

## Pilot 验收清单

- [ ] Docker Compose 镜像构建完成，`fleetent platform init-config` 成功。
- [ ] `fleetent platform upgrade --dry-run` 成功。
- [ ] SQLite backup 已创建。
- [ ] 服务启动成功，`GET /health` 返回 200。
- [ ] 默认 agent 可响应一次测试消息。
- [ ] agent 到 KB 绑定符合 Pilot scope。
- [ ] Google Drive / Confluence connector `check` 通过或失败原因明确。
- [ ] KB connector `sync --dry-run` 通过。
- [ ] KB connector `sync` 完成并可查询 `status`。
- [ ] `GET /admin/stats/agents/<agent_id>/overview` 可查询测试 run 的聚合统计。
- [ ] `GET /admin/stats/agents/<agent_id>/tools` 可查询工具调用概览。
- [ ] `GET /admin/stats/sessions/<session_id>/trace` 可 drill-down 到单次会话 trace。
- [ ] `fleetent platform diagnostics export` 可生成脱敏诊断包。
- [ ] `fleetent platform diagnostics retention dry-run` 可输出候选数量。
- [ ] 回滚负责人和问题上报路径已确认。
- [ ] （managed）`fleetent platform nodes list` 显示 node 已注册且状态正常。
- [ ] （managed）`nodes show <node-id>` 的 desired_agents 与 actual_agents 已收敛。
- [ ] （managed）IM 对话经 node IM-edge 完成一次端到端测试（非 `fleetent agent run` 直连）。

## 问题上报包

问题上报包应包含：

- fleetent 版本、commit SHA 和部署时间。
- `fleetent platform upgrade --dry-run` 输出摘要。
- `GET /health` 结果。
- connector `check` / `status` 的脱敏输出。
- stats overview / tools / session trace 的脱敏输出。
- diagnostics export 生成的本地包路径。
- 回滚是否执行、使用的 SQLite backup 路径和回滚后 health check 结果。

问题上报包不包含真实 secret、token、credential payload、用户完整 prompt / reply、KB 文档正文、SQLite 主库或 SQLite backups。
