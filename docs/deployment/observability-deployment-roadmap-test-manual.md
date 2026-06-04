# Observability and Deployment Roadmap 人工测试手册

本手册用于把
[observability-deployment-roadmap.md](../capabilities/roadmaps/observability-deployment-roadmap.md)
从“本地自动化已通过”推进到 Pilot `Go` 所需的人工证据。它覆盖 Observability、Diagnostics、
Deployment / Config 和 Pilot verification；Memory / KB / Reflection 的业务验收见
[intelligence-roadmap-test-manual.md](intelligence-roadmap-test-manual.md)。

## 0. 当前验证记录

2026-06-04 已完成一次本机 `local-as-server` 人工验证，结论为：

```text
observability_deployment_acceptance:
  decision: Go for Observability / Deployment
  scope: local-as-server, single-node
  evidence:
    automated_tests: passed
    config_validation: passed
    docker_compose: passed
    health_check: passed
    backup_upgrade_restore: passed
    observability_queries: passed
    diagnostics_export_redaction: passed
    pilot_verification_report: generated
  notes:
    - This is not full-project Pilot Go.
    - Real LLM / embedding / rerank / Google Drive / Confluence smoke remain owned by Runtime / Model Router and Intelligence roadmap validation.
    - The app container does not have Docker CLI / socket access, so sandbox effective mode is off. This is not an Observability / Deployment blocker.
```

## 1. Go 判定边界

达到 `Go` 需要同时满足：

- 配置检查、Docker Compose Pilot 入口、SQLite backup / upgrade / restore drill 可复核。
- 服务可以启动，health check 和 admin CLI 可用。
- trace、usage、performance summary 可查询，并能定位至少一次测试 run。
- diagnostics package 可导出，manifest 完整，且不包含 secret、SQLite 主库、SQLite backup、完整 prompt / reply 或 KB 文档正文。
- Pilot verification report 可生成，真实 smoke 的 pass / fail / skipped 状态明确。
- 没有 unresolved `Pilot blocker`；所有 Docs gap、Enhancement、Out-of-scope 均有 owner 和后续处理方式。

## 2. 前置条件

本机作为服务器：

- 可以把当前机器当作单节点准生产环境完成本手册的大部分人工验证。
- 推荐使用 Docker Compose 在本机启动 Pilot 入口，这样能同时覆盖部署入口、配置初始化、volume、backup 和
  diagnostics 路径。
- 源码环境下的 `uv run uvicorn fleetent.server:app --reload` 只作为开发模式补充证据；如果用它替代
  Docker Compose，需要把 `FLEETENT_DOCKER_COMPOSE_SMOKE` 记录为 skipped，并说明原因。
- 本机模式可以验证 config validation、SQLite backup / upgrade / restore drill、trace / usage /
  performance 查询、diagnostics export / redaction 和 Pilot verification report。
- 本机模式不能替代生产主机安全基线、客户网络策略、多节点部署、长期容量压测、真实公网回调和企业运维流程。

记录环境：

```text
environment:
  name: local-as-server
  host: 127.0.0.1
  operator:
  branch:
  commit_sha:
  started_at:
  data_dir:
  config_dir:
  compose_project:
```

确认工具：

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
uv --version
docker compose version
```

通过标准：

- branch / commit SHA 与验收记录一致。
- `git status --short` 不显示 `.env`、credential 文件、SQLite DB、backup 或 diagnostics package。
- Docker Compose 可用。
- 如果 `/health` 显示 sandbox `mode=off` 且 `docker_available=false`，记录为 Runtime / Sandbox note；
  除非本次 Observability / Deployment 验收明确要求 sandbox 执行，否则不作为本手册的 blocker。

## 3. 自动化快验

先跑 observability / deployment 代表性测试：

```bash
uv run pytest tests/integration/test_trace_events.py \
  tests/integration/test_usage_summary.py \
  tests/integration/test_performance_summary.py \
  tests/integration/test_observability_agent_contracts.py \
  tests/integration/test_observability_logging.py \
  tests/integration/test_diagnostics_retention.py \
  tests/unit/test_diagnostics_export.py \
  tests/integration/test_deployment_docs.py \
  tests/integration/test_upgrade_script.py \
  tests/unit/test_config_validation.py \
  tests/unit/test_pilot_readiness_reports.py \
  tests/integration/test_pilot_capability_contracts.py \
  -q
```

通过标准：

- 所有测试通过。
- 如果失败，先按失败项定位到 trace / diagnostics / config / upgrade / report 其中一个能力域。

## 4. 配置与 Secret 检查

目标：

- 配置只保存非敏感策略。
- secret 只通过环境变量或受控 secret 文件注入。
- connector credential 使用 `credential_ref`。

执行：

```bash
test -f config/settings.yaml
test -f config/mcp.servers.yaml || true
uv run fleetent-admin validate-config --profile pilot --format json
uv run fleetent-admin kb connectors list
```

人工复核：

- `config/settings.yaml` 不包含明文 API key、OAuth token、connector token 或 password。
- `config/mcp.servers.yaml` 只包含 MCP server definition 和非敏感引用。
- `fleetent-admin kb connectors list` 输出不包含 token、credential payload 或文档正文。

失败分类：

- secret 出现在配置、CLI 输出、日志、trace 或 diagnostics：No-Go。
- `validate-config` 不可运行：`Pilot blocker`。
- 配置可用但说明不足：Docs gap。

## 5. Docker Compose Pilot 入口

目标：

- Pilot 默认部署入口可启动。
- init-config 不覆盖已有配置。
- admin CLI 在 Compose 容器内可用。

执行：

```bash
docker compose run --rm --entrypoint uv fleetent run fleetent-admin --help
docker compose run --rm --entrypoint uv fleetent run fleetent-admin init-config
docker compose up -d
docker compose ps
```

`fleetent` 镜像的默认 entrypoint 会启动 Uvicorn server；容器内运行 CLI 时必须用 `--entrypoint uv`
覆盖默认 entrypoint。

如果有 HTTP health endpoint，执行：

```bash
curl -fsS http://127.0.0.1:8765/health || true
```

人工复核：

- `.env`、`config/settings.yaml`、`config/mcp.servers.yaml`、`data/`、`data/logs/`、
  `data/diagnostics/` 和 `secrets/` 的创建或跳过行为符合预期。
- 服务进程保持运行。
- health check 或等效 CLI smoke 可执行。

失败分类：

- 服务无法启动或 CLI 不可用：`Pilot blocker`。
- health endpoint 未定义但 CLI smoke 可用：Docs gap。
- Compose profile 或端口说明不清楚：Docs gap。

## 6. SQLite Backup / Upgrade / Restore Drill

目标：

- migration 前有 backup。
- backup 失败不会继续 migration。
- migration 失败时保留 backup。
- operator 能完成一次手动 restore drill。

执行 dry-run：

```bash
uv run python scripts/upgrade.py --dry-run
```

执行 backup-only：

```bash
uv run python scripts/upgrade.py --backup-only
```

执行 upgrade：

```bash
uv run python scripts/upgrade.py
```

人工 restore drill：

```bash
ls -lt data/backups
test -f data/backups/<timestamp>/fleetent.db
```

如需在测试环境恢复，先停止服务，再由 operator 将 backup 复制回测试 DB 路径，并记录操作：

```bash
stamp=$(date +%Y%m%d-%H%M%S)
mkdir -p "data/backups/manual-before-restore-${stamp}"
cp data/fleetent.db "data/backups/manual-before-restore-${stamp}/fleetent.db"
docker compose down
cp data/backups/<timestamp>/fleetent.db data/fleetent.db
docker compose up -d
```

通过标准：

- dry-run 输出 database URL、backup 路径和 migration 计划，不创建 backup，不运行 Alembic。
- backup-only 创建 `data/backups/<timestamp>/fleetent.db`，不运行 migration。
- upgrade 在 backup 成功后运行 migration。
- restore 覆盖当前 DB 前，先额外保存一份当前 DB 的 manual backup。
- restore drill 后服务可再次启动。

失败分类：

- backup 不存在仍继续 migration：No-Go。
- migration 失败且 backup 丢失：No-Go。
- restore 步骤无法复现：`Pilot blocker`。

## 7. Observability 查询

目标：

- operator 能查询 trace、usage、performance。
- 能定位一次具体 run。
- runtime event payload 只暴露可排障摘要，不泄漏完整 prompt / reply 或 secret。

准备一次测试 run 后执行：

```bash
uv run fleetent-admin observability traces --limit 20
uv run fleetent-admin observability traces --event-type agent_run_failed --limit 50
uv run fleetent-admin observability usage --limit 100
uv run fleetent-admin observability performance --limit 100
```

人工复核：

- traces 显示 run id、event type、时间、状态和 payload key summary。
- usage 显示 run count、token usage 和 by-model summary。
- performance 显示失败率、延迟、LLM / tool / fallback / permission 指标。
- 可以拿一条 run id 追踪到关键事件。

失败分类：

- trace / usage / performance 不可查询：`Pilot blocker`。
- 查询可用但过滤条件或输出说明不足：Docs gap。
- 需要 dashboard UI 才更方便：Enhancement。

## 8. Diagnostics Export / Redaction

目标：

- diagnostics package 可导出。
- manifest 能说明包含哪些 artifact。
- package 不包含 secret、SQLite 主库、SQLite backup、完整 prompt / reply、tool payload、memory 内容或 KB 文档正文。

执行：

```bash
uv run fleetent-admin diagnostics export
uv run fleetent-admin diagnostics retention dry-run
```

人工复核：

- package 包含 manifest、logs summary、trace / usage / performance summary、connector status、environment 和 config summary。
- package 不包含 `data/fleetent.db`、`data/backups/`、credential 文件、secret 文件、完整 prompt / reply、KB chunks。
- redaction 后仍能定位错误类型、run id、connector id 和 skip reason。

建议检查：

```bash
find data/diagnostics -maxdepth 3 -type f | sort | tail -50
```

失败分类：

- diagnostics 泄漏 secret、正文、DB 或 backup：No-Go。
- diagnostics 不能导出：`Pilot blocker`。
- manifest 缺少 artifact 说明：Docs gap。

## 9. Pilot Verification Report

目标：

- 自动化证据包可生成。
- report 明确列出 command results、capability evidence、real smoke evidence、issues 和 final recommendation。
- 真实 smoke 的 skipped / failed 项有可追踪原因。

执行：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

默认产物：

```text
reports/pilot-capability-verification/pilot-capability-verification.md
reports/pilot-capability-verification/pilot-capability-verification.json
```

人工复核：

- Markdown 可读，JSON 可作为附件保存。
- `Real Smoke Evidence` 中每一项都是 `passed`、`failed` 或 `skipped`。
- `Issues` 使用 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope 分类。
- final recommendation 与人工验收记录一致。

失败分类：

- report 无法生成：`Pilot blocker`。
- report 与实际人工证据矛盾：`Pilot blocker`，先修正证据导入或报告生成逻辑。
- report 可生成但缺少某个人工 artifact 导入：Docs gap 或 Enhancement。

## 10. 真实 Smoke 状态复核

真实 smoke 变量：

```bash
export FLEETENT_REAL_LLM_SMOKE=1
export FLEETENT_REAL_EMBEDDING_SMOKE=1
export FLEETENT_REAL_RERANK_SMOKE=1
export FLEETENT_GOOGLE_DRIVE_SMOKE=1
export FLEETENT_CONFLUENCE_SMOKE=1
export FLEETENT_DOCKER_COMPOSE_SMOKE=1
```

复核规则：

- 已配置凭据且网络允许时，应跑到 `passed` 或 `failed`，不能仍是 missing flag。
- 没有客户批准的真实凭据时，记录为 `skipped: credentials not configured`，并由 Pilot owner 决定是否允许 `Go`。
- Docker Compose smoke 对 Go 更关键；如果部署入口本身不可用，应归为 `Pilot blocker`。

## 11. 汇总到 Go 证据

验收记录模板：

```text
observability_deployment_acceptance:
  automated_tests:
    status:
  config_validation:
    status:
    evidence:
  docker_compose:
    status:
    evidence:
  backup_upgrade_restore:
    status:
    evidence:
  observability_queries:
    status:
    evidence:
  diagnostics:
    status:
    evidence:
  pilot_verification_report:
    status:
    markdown_path:
    json_path:
    final_recommendation:
  issues:
  decision:
```

`Go` 需要没有 unresolved `Pilot blocker`，且 diagnostics / config / trace / report 均无敏感信息泄漏。

如果本机验证已经达到 `Go`，但全项目报告仍因真实 LLM / embedding / rerank / Google Drive / Confluence
显示 `skipped` 而给出 `Conditional Go`，不要降级本 roadmap 结论；把这些 skipped 项转交给对应 roadmap
继续验证。
