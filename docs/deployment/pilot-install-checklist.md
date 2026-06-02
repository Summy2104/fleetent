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
- 已准备 Python、uv、SQLite、Git 和网络代理配置。
- 已确认服务端口未被占用，运行用户对 `data/`、`config/`、`logs/` 有读写权限。
- 已确认问题上报渠道和回滚负责人。

## 配置与 Secret 边界

配置文件只保存非敏感设置和 credential reference：

- `config/settings.yaml`：保存 `database_url`、默认 agent、knowledge base、connector scope、diagnostics
  retention 开关等非敏感配置。
- Google Drive / Confluence credential 使用 `credential_ref`，例如 `env:FLEETENT_CONNECTOR_TOKEN` 或
  `file:///etc/fleetent/secrets/connector-token.json`。
- 真实 secret 文件、环境变量注入方式和权限由部署方管理。

不要把真实 secret、token、credential payload 写入 settings、日志、trace、diagnostics package、issue 或测试 fixture。
问题上报包不包含真实 secret。

## 安装、升级与备份

安装依赖：

```bash
uv sync
```

升级前先 dry-run：

```bash
uv run python scripts/upgrade.py --dry-run
```

dry-run 通过后执行升级脚本。脚本会在 SQLite backup 成功后运行 `alembic upgrade head`：

```bash
uv run python scripts/upgrade.py
```

只做备份、不迁移：

```bash
uv run python scripts/upgrade.py --backup-only
```

验收点：

- dry-run 输出 database URL、backup 路径和 migration 计划。
- 非 dry-run 模式下，SQLite backup 写入 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`。
- 只有 backup 成功后才运行 `alembic upgrade head`。
- migration 失败时保留 backup，不自动 rollback。

## 启动与健康检查

启动服务：

```bash
uv run uvicorn fleetent.server:app --host 0.0.0.0 --port 8000
```

健康检查：

```text
GET /health
```

验收点：

- 服务在预期端口启动。
- `GET /health` 返回 200。
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
uv run fleetent-admin kb connectors sync eng-drive
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
2. 确认最近一次 SQLite backup 路径，例如 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`。
3. 替换当前 DB 文件，例如把 backup DB 复制回 `data/fleetent.db`。
4. 重启 fleetent 服务。
5. 再次运行 `GET /health`。
6. 运行 `uv run fleetent-admin observability traces --event-type agent_run_failed --limit 20` 查看回滚后是否仍有失败事件。

回滚不自动删除 diagnostics package 和 logs；保留它们用于问题上报。

## Pilot 验收清单

- [ ] 依赖安装完成，`uv sync` 成功。
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
