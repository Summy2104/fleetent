# Pilot 人工验收指南

本指南用于 Pilot 安装完成后的测试环境人工验收，判断当前 fleetent 是否可以进入小范围真实用户试用。它是
[pilot-install-checklist.md](pilot-install-checklist.md) 的后续步骤：安装清单负责“装起来”，本指南负责“验证能不能试用”。
如果需要一份从部署到验收的逐步执行流程，优先使用 [pilot-runbook.md](pilot-runbook.md)；本指南负责定义
验收标准、Go / No-Go 判定和报告模板。

本指南不替代自动化测试，不要求默认连接真实 LLM、embedding、Google Drive 或 Confluence。真实外部依赖 smoke
必须显式 opt-in；凭据或环境变量未配置时记录为 `skipped: credentials not configured`，不视为默认失败。

进入人工验收前，先生成自动化验证报告作为辅助证据：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

默认报告产物为 `pilot-capability-verification.md` 和 `pilot-capability-verification.json`。Markdown 给人工
review；JSON 给 CI 或后续 dashboard ingestion。报告会列出七个 owner capability 的测试证据、默认命令结果、
真实 smoke 的 pass/fail/skipped 状态、`Pilot blocker` / Docs gap / Enhancement / Out-of-scope 分类，以及
Go / `Conditional Go` / No-Go 建议。真实 smoke 必须显式设置 opt-in flag，例如 `FLEETENT_REAL_LLM_SMOKE=1`
和 `FLEETENT_GOOGLE_DRIVE_SMOKE=1`，并提供对应 credential ref；缺少任一项时应清晰 skipped。

## 1. 验收目标与判定标准

验收目标：

- 验证测试环境能完成配置加载、SQLite 升级、备份、恢复演练、服务启动和基础 health check。
- 验证 operator 能通过 `fleetent platform` 查询 observability、导出 diagnostics，并定位一次测试 run。
- 验证 memory、long-term context、reflection、knowledge base、vector store 的 Pilot MVP 基础链路可用。
- 验证真实外部依赖的状态被明确记录为 `passed`、`failed` 或 `skipped`。
- 输出一份可追踪的验收报告，明确 Pilot blocker、docs gap、enhancement 和 out-of-scope。

Go / Conditional Go / No-Go 标准：

| 判定 | 标准 |
| --- | --- |
| Go | 核心本地链路、配置检查、SQLite backup / upgrade / restore drill、服务启动、health check、CLI、observability、diagnostics、memory、long-term context、reflection、KB local、vector reindex 全部通过；真实外部 smoke 至少 `check` 通过或明确 `skipped`。 |
| Conditional Go | 核心本地链路通过，但真实 LLM、embedding、Google Drive 或 Confluence smoke 因凭据、网络、scope 或测试数据问题失败；报告中必须记录 workaround、owner 和复测时间。 |
| No-Go | 配置加载、服务启动、数据库 migration、backup / restore、diagnostics、observability 查询、memory 基础链路、KB local 或 vector reindex 任一不可用；或发现 secret 泄漏到配置、日志、trace、diagnostics package、issue。 |

## 2. 环境前置条件

执行前确认：

- 已按 [pilot-install-checklist.md](pilot-install-checklist.md) 完成安装、依赖同步和基础配置。
- 当前分支、commit SHA、部署包版本和目标环境名称已记录。
- operator 有测试环境 shell 权限、服务启停权限、`data/` 和 `config/` 读写权限。
- Docker Compose 可用，且 `docker compose run --rm fleetent uv run fleetent platform --help` 能输出帮助。
- 服务端口未被占用，测试环境允许访问企业批准的 LLM / embedding endpoint。
- 测试数据不包含真实敏感客户数据；如必须使用真实企业数据，先确认数据 owner 和脱敏策略。

记录项：

```text
environment:
  name:
  host:
  operator:
  started_at:
  branch:
  commit_sha:
  data_dir:
  config_dir:
```

## 3. 配置与 Secret 检查

检查目标：

- `agents/<agent-id>/agent.yaml` 只包含 agent、model、MCP server、knowledge binding、connector、provider 等非敏感配置。
- Google Drive / Confluence credential 使用平铺的 `*_env` 引用，例如
  `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`、`FLEETENT_CONFLUENCE_TOKEN`。
- MCP server credential 只包含 `api_key_env` 等非敏感引用。
- `.env`、系统环境变量或受控 secret 文件只留在测试环境本机，不进入 git、trace、日志、diagnostics package 或 issue。
- `database_url` 指向测试环境管理库 SQLite 文件，例如 `sqlite:////app/management.db`。

建议检查：

```bash
git status --short
test -f agents/<agent-id>/agent.yaml
GET /admin/kb/connectors
```

通过标准：

- `git status --short` 不显示误提交的 secret、`.env`、credential 文件或 data 文件。
- `GET /admin/kb/connectors` 返回的 connector 摘要不包含 token、credential payload 或文档正文。
- `credential_ref` 指向的文件权限和环境变量注入方式已由 operator 单独记录。

## 4. SQLite Backup / Upgrade / Restore Drill

执行 dry-run：

```bash
uv run fleetent platform upgrade --dry-run
```

通过标准：

- 输出 database URL、backup 路径和 migration 计划。
- dry-run 不创建 backup，不运行 Alembic，不要求 DB 文件存在。

执行 upgrade：

```bash
uv run fleetent platform upgrade
```

通过标准：

- SQLite backup 写入 `data/backups/YYYYMMDD-HHMMSS/`，按数据目录结构镜像全部物理库（管理库 `management.db` + per-tenant / per-agent 子目录下各库，含 WAL sidecar）。
- backup 成功后才运行 `alembic upgrade head`。
- migration 成功后服务仍能启动；migration 失败时保留 backup 且命令返回非 0。

执行 backup-only：

```bash
uv run fleetent platform upgrade --backup-only
```

通过标准：

- 只创建 backup，不运行 Alembic。
- backup 文件路径已记录。

执行 restore drill：

1. 停止 fleetent 服务。
2. 记录当前数据目录和 restore 来源备份批次目录。
3. 用同一备份批次按镜像结构把全部库复制回各自位置（如 `…/management.db` → `<FLEETENT_HOME>/management.db`，以及 `tenants/<tenant>/agents/<agent>/data/` 下各库），不混用不同时间点的备份。
4. 重启 fleetent 服务。
5. 再次执行 `GET /health`。
6. 运行 observability 查询确认恢复后可查询事件。

恢复后命令：

```bash
GET /admin/observability/traces?event_type=agent_run_failed&limit=20
```

通过标准：

- restore drill 不要求保留 drill 期间产生的业务变更，但必须证明 backup 可用于恢复启动。
- 失败时记录为 No-Go 候选，除非能在同一验收窗口内修复并复测通过。

## 5. 服务启动、Health Check 与 CLI 可用性

启动服务：

```bash
docker compose up -d
```

检查 health：

```bash
curl -fsS http://127.0.0.1:8765/health
```

检查 CLI：

```bash
docker compose run --rm fleetent uv run fleetent platform init-config --dry-run
uv run fleetent platform --help
GET /admin/observability/traces?limit=5
uv run fleetent "hello"
```

`fleetent platform serve` 是主要服务启动入口；`uvicorn fleetent.server:app` 可直接作为 ASGI 应用访问，仅用于开发模式。

通过标准：

- 服务启动无配置错误、DB migration 错误或 secret 打印。
- `/health` 返回 200。
- `fleetent platform` 子命令可执行。
- CLI agent 可完成一次最小 run；如果真实 LLM 未配置，应记录为 `skipped: real LLM route not configured`
  或 `failed`，并说明是否影响 Go 判定。

## 6. Observability / Diagnostics 验收

查询 traces：

```bash
GET /admin/observability/traces?limit=20
GET /admin/observability/traces?event_type=agent_run_failed&limit=50
```

查询 usage：

```bash
GET /admin/observability/usage?limit=100
```

查询 performance：

```bash
GET /admin/observability/performance?limit=100
```

导出 diagnostics：

```bash
uv run fleetent platform diagnostics export
uv run fleetent platform diagnostics retention dry-run
```

通过标准：

- `traces` 输出事件元数据和 payload key summary，不输出 prompt、reply、tool payload 或 credential 原值。
- `usage` 输出 run count、token usage 和 by-model summary。
- `performance` 输出失败率、延迟、LLM / tool / fallback / permission 指标。
- diagnostics package 包含 manifest、logs、trace / usage / performance 摘要、connector status、environment 和 config summary。
- diagnostics package 不包含 memory 内容、KB 文档正文 / chunks、SQLite 主库、SQLite backups、credential 文件内容或 token。
- `diagnostics retention dry-run` 只输出候选数量，不删除数据。

## 7. Memory 验收

默认本地验收使用 deterministic / mock evaluation，不连接真实 LLM：

```bash
uv run pytest tests/evaluation/test_memory_extraction_eval.py -q
```

人工检查：

- 选择一个测试 user id，完成一次包含用户偏好或背景信息的测试对话。
- 再发起一次与该偏好相关的问题，确认 memory search 能返回相关 User Memory。
- 运行 memory maintenance dry-run，确认候选项只被规划，不会默认删除或改写 User Memory。

可用 public API 记录项：

```text
memory:
  user_id:
  extraction_result:
  search_query:
  search_result_count:
  maintenance_dry_run:
```

真实 LLM memory extraction smoke：

- 只有设置 `FLEETENT_EVAL_REAL_LLM=1` 且 provider API key 完整时才手动运行。
- 未配置时记录 `skipped: credentials not configured`。
- 失败时记录 provider、route、错误摘要和是否有 deterministic fallback 证据。

通过标准：

- deterministic evaluation 通过。
- User Memory 能写入、检索，并能按 owner 边界维护。
- maintenance dry-run 不直接修改 memory。

## 8. Long-term Context 验收

默认本地验收：

```bash
uv run pytest tests/evaluation/test_long_term_context_eval.py -q
```

人工检查：

- 准备至少一条 User Memory 和一个 KB local source。
- 运行一次查询，确认注入上下文同时包含 memory / knowledge source attribution。
- 降低可用 token budget 后复测，确认上下文按 budget 截断并记录 budget decision。
- 禁用或清空 KB 后复测，确认 long-term context 仍可返回 memory 内容，不因 KB 无结果失败。

真实 provider smoke：

- 只有设置 `FLEETENT_EVAL_REAL_LONG_TERM_CONTEXT=1` 且 LLM / KB / embedding 配置完整时才手动运行。
- 未配置时记录 `skipped: credentials not configured`。

通过标准：

- deterministic evaluation 通过。
- 注入文本与 source attribution 可被 observability 追踪。
- KB 缺失或未启用不阻塞 memory 注入。

## 9. Reflection 验收

默认本地验收：

```bash
uv run pytest tests/evaluation/test_reflection_report_eval.py -q
```

人工检查：

- 基于最近 7 天测试 trace 运行 reflection report smoke。
- 确认 report 包含 finding type、summary、evidence ids 和 metadata。
- 确认报告保存时不持久化完整 transcript。
- 对 memory_candidate / memory_conflict 生成 User Memory maintenance proposals。
- 确认 proposal 默认是 pending，不自动改写 User Memory；apply 只能通过 owner-approved lifecycle。

真实 route smoke：

- 只有设置 `FLEETENT_EVAL_REAL_REFLECTION=1` 且本地 fixture / config 完整时才手动运行。
- 未配置时记录 `skipped: credentials not configured`。

通过标准：

- deterministic report evaluation 通过。
- reflection 能生成报告，并能生成 User Memory maintenance proposals。
- `suggest_shared_memory_or_kb` 不写 User Memory。

## 10. Knowledge Base 验收

### 10.1 Local source

默认本地验收：

```bash
uv run pytest tests/evaluation -x -q
```

人工检查：

- 准备一个测试 local directory，包含 `.txt`、`.md` 或 `.html` 文档。
- 使用 KB local sync planner 生成 dry-run plan，确认 new / changed / unchanged / missing 动作符合预期。
- 执行 local sync 后，运行 KB search，确认能返回相关 chunk。
- 删除或修改源文件后再次 dry-run，确认 archive / reingest 计划符合预期。

通过标准：

- local source 可 sync 和 search。
- sync plan / execute 分离；dry-run 不写 KB、source state 或 vector index。
- search 不返回未绑定 KB 或不在 scope 内的内容。

### 10.2 Google Drive

检查配置：

```bash
GET /admin/kb/connectors
POST /admin/kb/connectors/<google_drive_connector_id>/check
POST /admin/kb/connectors/<google_drive_connector_id>/sync  # body: {"dry_run": true}
GET /admin/kb/connectors/<google_drive_connector_id>/status
```

真实 sync smoke：

```bash
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  POST /admin/kb/connectors/<google_drive_connector_id>/sync  # body: {"dry_run": false}
```

需要补跑实体抽取时：

```bash
uv run fleetent kb-extract --config $FLEETENT_HOME/tenants/default/kb/kb-service.yaml --kb <kb_id> --wait
```

执行规则：

- verification report 真实 smoke 使用 `FLEETENT_GOOGLE_DRIVE_SMOKE=1`；手动 CLI execute sync 还必须设置
  `FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1`，并带 `--yes --pilot-fixture`。
- 只有 `credential_ref`、folder id 和网络权限完整时才允许真实 sync 成功。
- 未配置时记录 `skipped: credentials not configured`。
- 手动实体抽取入口固定为 `fleetent kb-extract`，不再使用 platform CLI。
- `check` 返回 `credential_missing`、`credential_invalid`、`auth_failed` 或 `scope_unreachable` 时，记录为 failed 或 Conditional Go 候选，不能静默跳过。

### 10.3 Confluence

检查配置：

```bash
GET /admin/kb/connectors
POST /admin/kb/connectors/<confluence_connector_id>/check
POST /admin/kb/connectors/<confluence_connector_id>/sync  # body: {"dry_run": true}
GET /admin/kb/connectors/<confluence_connector_id>/status
```

真实 sync smoke：

```bash
FLEETENT_CONFLUENCE_EXECUTE_SYNC=1 \
  POST /admin/kb/connectors/<confluence_connector_id>/sync  # body: {"dry_run": false}
```

执行规则：

- verification report 真实 smoke 使用 `FLEETENT_CONFLUENCE_SMOKE=1`；手动 CLI execute sync 还必须设置
  `FLEETENT_CONFLUENCE_EXECUTE_SYNC=1`，并带 `--yes --pilot-fixture`。
- 只有 base URL、username、`credential_ref`、space / page scope 和网络权限完整时才允许真实 sync 成功。
- 未配置时记录 `skipped: credentials not configured`。
- 输出不得包含 API token、credential payload 或页面正文。

## 11. Vector Store / Embedding / Rerank Smoke

默认本地验收：

```bash
uv run pytest tests/evaluation -x -q
```

reindex 检查：

- 对 memory namespace 执行 dry-run，确认将从 User Memory source of truth 枚举待索引记录。
- 对 KB namespace 执行 dry-run，确认将从 KB chunks source of truth 枚举待索引记录。
- 执行 rebuild 后，确认目标 namespace 先清空再写入当前 source records。
- 复测 search，确认能返回当前记录，不返回已删除记录。

真实 embedding smoke：

- 只有设置 `FLEETENT_EVAL_REAL_EMBEDDING=1` 且 endpoint、model、API key、dimensions 完整时才手动运行。
- 未配置时记录 `skipped: credentials not configured`。
- 失败时记录 provider backend、endpoint host、model、dimensions、错误摘要；不要记录 API key。

Rerank smoke：

- 当前 rerank provider boundary 已定义，并已接入 KB hybrid search 的显式 `rerank=True` 路径；默认
  `rerank.backend=disabled`，不会静默调用真实外部服务。
- 如果 `rerank.backend=disabled`，记录 `skipped: rerank disabled by config`。
- 如果显式配置 deterministic 或 HTTP rerank provider，验证 provider smoke、错误处理和 KB hybrid rerank
  能返回稳定结果；真实 rerank provider 失败通常记为 Conditional Go，除非影响默认本地链路。

## 12. 真实外部依赖记录规则

每个真实外部 smoke 都必须使用统一状态：

| 状态 | 使用场景 | Go 判定影响 |
| --- | --- | --- |
| `passed` | 显式 opt-in 已开启，凭据和网络完整，smoke 成功。 | 支持 Go。 |
| `skipped` | 显式 opt-in 未开启，或凭据未配置。 | 不视为默认失败；报告必须写明原因。 |
| `failed` | 显式 opt-in 已开启，但认证、scope、网络、provider 响应或数据验证失败。 | 核心链路不受影响时通常是 Conditional Go；如果影响默认本地链路则 No-Go。 |

记录模板：

```text
external_smoke:
  name:
  opt_in_env:
  status: passed | skipped | failed
  reason:
  owner:
  next_action:
  evidence:
```

## 13. 故障记录模板

```text
issue_id:
title:
category: pilot_blocker | docs_gap | enhancement | out_of_scope
status: open | fixed | accepted_risk | deferred
severity: critical | high | medium | low
owner:
found_at:
environment:
command_or_step:
expected:
actual:
sanitized_evidence:
workaround:
go_impact: go | conditional_go | no_go
retest_command:
retest_result:
```

证据边界：

- 可以附脱敏日志、trace metadata、payload key summary、diagnostics package 路径、命令 exit code。
- 不要附真实 secret、token、credential payload、完整 prompt / reply、KB 文档正文、SQLite 主库或 SQLite backups。

## 14. 验收报告模板

```text
pilot_acceptance_report:
  environment:
  operator:
  started_at:
  completed_at:
  branch:
  commit_sha:
  final_decision: Go | Conditional Go | No-Go
  decision_reason:
  core_checks:
    config_and_secret:
    sqlite_backup_upgrade_restore:
    service_health:
    cli:
    observability:
    diagnostics:
    memory:
    long_term_context:
    reflection:
    knowledge_base_local:
    vector_reindex:
  external_smoke:
    real_llm:
    real_embedding:
    google_drive:
    confluence:
    rerank:
  issues:
    pilot_blockers:
    docs_gaps:
    enhancements:
    out_of_scope:
  accepted_risks:
  next_retest_at:
```

## 15. 问题分类规则

| 分类 | 定义 | 处理规则 |
| --- | --- | --- |
| Pilot blocker | 阻止小范围真实用户试用的问题，例如服务无法启动、DB migration 不可用、diagnostics 不脱敏、memory / KB local 基础链路不可用、secret 泄漏。 | 必须修复并复测后才能 Go。 |
| Docs gap | 功能可用，但操作说明、错误解释、记录模板或排障路径不清晰。 | 可 Conditional Go，但必须补文档 owner 和完成时间。 |
| Enhancement | Pilot 可用性不被阻塞的增强，例如 UI、scheduler、credential store、真实 rerank 质量评估、graph / rerank 默认检索策略产品化。 | 不阻塞第一次 Pilot 验收；进入后续 spec 评估。 |
| Out-of-scope | 非本 owner 范围或本 change 明确不处理的事项，例如客户网络策略、企业 IdP、生产 secret manager 选型。 | 记录依赖 owner，不作为本次验收失败原因。 |

增强 specs 可以与 Pilot 验收并行推进，但 Pilot 后增强不默认阻塞第一次 Pilot 验收。验收反馈应先按上述分类进入
follow-up loop，再决定是否新增或调整 OpenSpec change。
