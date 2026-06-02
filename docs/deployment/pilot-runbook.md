# Pilot 部署与人工验收 Runbook

本 runbook 面向第一次 Pilot 测试环境部署和验收。它把安装、升级、启动、分模块 smoke、问题记录和
Go / No-Go 判定串成一个可执行流程。

相关文档：

- [pilot-install-checklist.md](pilot-install-checklist.md)：安装、升级、备份和回滚清单。
- [pilot-acceptance-guide.md](pilot-acceptance-guide.md)：验收标准、外部 smoke 状态和报告模板。

执行原则：

- 先跑核心本地链路，再跑真实外部依赖 smoke。
- 真实 LLM、embedding、Google Drive、Confluence 和 rerank smoke 都必须显式 opt-in。
- 未配置凭据的真实外部 smoke 记录为 `skipped: credentials not configured`，不默认判失败。
- 任何输出、报告、issue 和 diagnostics package 都不得包含真实 secret、token、credential payload、
  完整 prompt / reply、KB 文档正文、SQLite 主库或 SQLite backups。

## 0. 准备验收记录

创建一份本次验收记录，后续每一步都把命令、结果和问题填进去。

```text
pilot_acceptance_report:
  environment:
    name:
    host:
    operator:
    started_at:
    branch:
    commit_sha:
    data_dir:
    config_dir:
  final_decision:
  core_checks:
  external_smoke:
  issues:
  accepted_risks:
```

通过标准：

- 记录里有环境名称、operator、branch、commit SHA 和开始时间。
- 本次验收使用测试数据；如必须使用真实企业数据，已确认数据 owner 和脱敏策略。

失败处理：

- 如果无法确定部署版本或环境，先停止验收，不要继续执行真实外部 smoke。

## 1. 确认代码版本和工作区

目的：确认测试环境部署的是可追踪版本，且没有误提交 secret 或本地运行数据。

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
```

预期结果：

- branch 和 commit SHA 已写入验收记录。
- `git status --short` 不显示 `.env`、credential 文件、`data/`、SQLite DB、backup 或 diagnostics package。

失败处理：

- 如果出现 secret 或 data 文件，先移除并确认 `.gitignore`，不要继续部署。
- 如果存在未提交业务改动，记录来源；无法确认来源时停止验收。

## 2. 准备配置和 Secret

目的：确认配置文件只保存非敏感配置，真实凭据由环境变量或受控 secret 文件注入。

```bash
test -f config/settings.yaml
test -f config/mcp.servers.yaml || true
test ! -f config/mcp.yaml
test ! -f config/cron.yaml
test ! -f config/webhooks.yaml
```

检查项：

- `config/settings.yaml` 包含 `database_url`、默认 agent、diagnostics、connector 和 provider 的非敏感配置。
- Google Drive / Confluence credential 使用 `credential_ref`，例如 `env:FLEETENT_CONNECTOR_TOKEN`
  或 `file:///etc/fleetent/secrets/google-drive-token.json`。
- MCP servers 使用独立 `config/mcp.servers.yaml`，不混入主 settings。
- 旧配置文件 `config/mcp.yaml`、`config/cron.yaml`、`config/webhooks.yaml` 不存在。

预期结果：

- 所有配置文件可读取。
- 配置文件、日志和验收记录不包含真实 token 或 credential payload。

失败处理：

- 旧配置文件存在时，先迁移或删除旧文件；不要同时维护新旧配置。
- credential_ref 指向文件不存在或权限过宽时，记录为配置问题并修正后复测。

## 3. 安装依赖

目的：安装项目依赖并确认 CLI 可执行。

```bash
uv sync --frozen --group dev
uv run fleetent --help
uv run fleetent-admin --help
```

预期结果：

- `uv sync --frozen --group dev` 成功。
- `fleetent` 和 `fleetent-admin` 都能输出帮助。

失败处理：

- 如果本机 `.venv` 损坏，删除 `.venv` 后重新执行 `uv sync --frozen --group dev`。
- 如果 `uv run` 找不到某个命令，检查 `pyproject.toml` 的 `[project.scripts]` 和 lock 文件。

## 4. SQLite Dry-run、备份和升级

目的：确认 migration 前有 backup，migration 失败时可保留恢复点。

```bash
uv run python scripts/upgrade.py --dry-run
uv run python scripts/upgrade.py --backup-only
uv run python scripts/upgrade.py
```

预期结果：

- dry-run 输出 database URL、backup 路径和 migration 计划，不创建 backup，不运行 Alembic。
- backup-only 只创建 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`，不运行 migration。
- upgrade 在 backup 成功后运行 `alembic upgrade head`。
- migration 成功后，backup 路径写入验收记录。

失败处理：

- DB 文件不存在且不是 dry-run 时，记录为部署准备失败。
- backup 失败时不要运行 migration。
- migration 失败时保留 backup，记录 Alembic 错误摘要和 backup 路径。

## 5. 启动服务和基础 Health Check

目的：确认服务可启动，基础 HTTP 和 CLI 链路可用。

启动服务：

```bash
uv run uvicorn fleetent.server:app --host 0.0.0.0 --port 8000
```

另开终端检查：

```bash
curl -fsS http://127.0.0.1:8000/health
uv run fleetent-admin observability traces --limit 5
uv run fleetent "hello"
```

预期结果：

- 服务启动日志无配置错误、DB migration 错误或 secret 打印。
- `/health` 返回 200。
- `fleetent-admin observability traces --limit 5` 可执行。
- `fleetent "hello"` 可完成一次最小 run；如果真实 LLM 未配置，记录为 `skipped` 或 `failed`，
  并说明是否影响本次 Go 判定。

失败处理：

- 服务无法启动：先看配置加载、database URL、migration 状态和启动日志。
- `/health` 非 200：记录 HTTP 状态、错误摘要和服务日志路径。
- CLI agent 失败：确认是 provider 未配置、网络问题还是 runtime 错误。

## 6. Observability 和 Diagnostics

目的：确认 operator 能定位一次 run，并导出脱敏诊断包。

```bash
uv run fleetent-admin observability traces --limit 20
uv run fleetent-admin observability traces --event-type agent_run_failed --limit 50
uv run fleetent-admin observability usage --limit 100
uv run fleetent-admin observability performance --limit 100
uv run fleetent-admin diagnostics export
uv run fleetent-admin diagnostics retention dry-run
```

预期结果：

- traces 输出事件元数据和 payload key summary，不输出 prompt、reply、tool payload 或 credential 原值。
- usage 输出 run count、token usage 和 by-model summary。
- performance 输出失败率、延迟、LLM / tool / fallback / permission 指标。
- diagnostics package 包含 manifest、logs、trace / usage / performance 摘要、connector status、
  environment 和 config summary。
- diagnostics package 不包含 memory 内容、KB 文档正文 / chunks、SQLite 主库、SQLite backups 或 credential 文件内容。
- retention dry-run 只输出候选数量，不删除数据。

失败处理：

- 如果 trace / usage / performance 不可查询，记录为 Pilot blocker 候选。
- 如果 diagnostics 泄漏 secret 或业务正文，直接记录为 No-Go。

## 7. Memory 验收

目的：确认 User Memory 可以抽取、检索和维护规划，且维护操作默认不直接改写。

默认本地验证：

```bash
uv run pytest tests/evaluation/test_memory_extraction_eval.py -q
```

人工流程：

1. 使用测试 user id 完成一次包含用户偏好或背景信息的测试对话。
2. 发起与该偏好相关的问题。
3. 查询 memory search 或相关 trace，确认返回对应 User Memory。
4. 运行 memory maintenance dry-run，确认只生成候选，不默认删除或改写 memory。

预期结果：

- deterministic evaluation 通过。
- User Memory 能写入、检索，并按 owner 边界维护。
- maintenance dry-run 不直接修改 memory。

失败处理：

- 抽取失败：确认 LLM route 是否配置；默认 deterministic evaluation 应先通过。
- 检索失败：检查 memory source of truth、vector index 和 query trace。
- maintenance 直接修改 memory：记录为 Pilot blocker。

## 8. Long-term Context 验收

目的：确认 memory 和 KB 可以被纳入长期上下文，并能按 token budget 受控注入。

```bash
uv run pytest tests/evaluation/test_long_term_context_eval.py -q
```

人工流程：

1. 准备至少一条 User Memory。
2. 准备一个 KB local source 并完成同步。
3. 运行一次查询，确认上下文包含 memory / knowledge source attribution。
4. 降低 token budget 后复测，确认记录 budget decision。
5. 禁用或清空 KB 后复测，确认 memory 注入仍可用。

预期结果：

- deterministic evaluation 通过。
- 注入文本与 source attribution 可被 observability 追踪。
- KB 缺失或未启用不阻塞 memory 注入。

失败处理：

- attribution 缺失：检查 query trace 和 long-term context 事件。
- budget 不生效：记录配置值、输入长度和实际注入长度。

## 9. Reflection 验收

目的：确认 reflection 能基于 trace 生成报告和 User Memory maintenance proposals。

```bash
uv run pytest tests/evaluation/test_reflection_report_eval.py -q
```

人工流程：

1. 准备最近 7 天内的测试 trace。
2. 运行 reflection report smoke。
3. 检查 report 是否包含 finding type、summary、evidence ids 和 metadata。
4. 检查报告保存时不持久化完整 transcript。
5. 检查 memory_candidate / memory_conflict 是否生成 pending proposal。

预期结果：

- deterministic report evaluation 通过。
- reflection 能生成报告和 pending User Memory maintenance proposals。
- `suggest_shared_memory_or_kb` 不写 User Memory。

失败处理：

- trace 不足时，先补 runtime event coverage 测试数据，不把 finding 质量作为第一判断。
- 如果 proposal 自动 apply，记录为 Pilot blocker。

## 10. Knowledge Base Local 验收

目的：确认本地知识库 source 可以 plan、sync、search，并保持 scope 隔离。

```bash
uv run pytest tests/evaluation -x -q
```

人工流程：

1. 准备测试 local directory，包含 `.txt`、`.md` 或 `.html` 文档。
2. 运行 local sync dry-run，确认 new / changed / unchanged / missing 动作符合预期。
3. 执行 local sync。
4. 运行 KB search，确认返回相关 chunk。
5. 修改或删除源文件，再次 dry-run，确认 reingest / archive 计划符合预期。

预期结果：

- local source 可 sync 和 search。
- dry-run 不写 KB、source state 或 vector index。
- search 不返回未绑定 KB 或不在 scope 内的内容。

失败处理：

- sync plan 不符合预期：记录源文件路径、plan 输出和 source state。
- search 返回越权内容：记录为 Pilot blocker。

## 11. Google Drive Connector 验收

目的：确认 Google Drive connector 配置可检查，真实同步在显式 opt-in 下运行。

检查流程：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <google_drive_connector_id>
uv run fleetent-admin kb connectors sync <google_drive_connector_id> --dry-run
uv run fleetent-admin kb connectors status <google_drive_connector_id>
```

真实 sync smoke：

```bash
FLEETENT_GOOGLE_DRIVE_SMOKE=1 uv run fleetent-admin kb connectors sync <google_drive_connector_id>
```

预期结果：

- list 输出 connector id、type、tenant、KB 和 scope，不输出 credential payload。
- check 返回 `ok`，或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、`scope_unreachable`。
- dry-run 不写 KB、source state 或 vector index。
- 真实 sync 只在 opt-in、credential_ref、folder id 和网络权限完整时执行。

失败处理：

- 凭据未配置：记录 `skipped: credentials not configured`。
- check 失败：记录状态、connector id、scope 和脱敏错误摘要。
- sync 失败：记录为 Conditional Go 候选，除非影响默认本地 KB 链路。

## 12. Confluence Connector 验收

目的：确认 Confluence connector 配置可检查，真实同步在显式 opt-in 下运行。

检查流程：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <confluence_connector_id>
uv run fleetent-admin kb connectors sync <confluence_connector_id> --dry-run
uv run fleetent-admin kb connectors status <confluence_connector_id>
```

真实 sync smoke：

```bash
FLEETENT_CONFLUENCE_SMOKE=1 uv run fleetent-admin kb connectors sync <confluence_connector_id>
```

预期结果：

- check 返回 `ok`，或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、`scope_unreachable`。
- 输出不包含 API token、credential payload 或页面正文。
- dry-run 和真实 sync 的结果写入脱敏 status。

失败处理：

- 凭据未配置：记录 `skipped: credentials not configured`。
- scope 无法访问：记录 space / page scope 的脱敏标识和错误摘要。

## 13. Vector Store / Embedding / Rerank 验收

目的：确认索引可重建，embedding provider smoke 可选，rerank 未接入时不误判为 blocker。

默认本地验证：

```bash
uv run pytest tests/evaluation -x -q
```

人工流程：

1. 对 memory namespace 执行 reindex dry-run，确认从 User Memory source of truth 枚举记录。
2. 对 KB namespace 执行 reindex dry-run，确认从 KB chunks source of truth 枚举记录。
3. 执行 rebuild，确认目标 namespace 先清空再写入当前 source records。
4. 复测 search，确认返回当前记录，不返回已删除记录。

真实 embedding smoke：

```bash
FLEETENT_EVAL_REAL_EMBEDDING=1 uv run pytest tests/evaluation -k embedding -q
```

预期结果：

- reindex rebuild 后 search 结果与 source of truth 一致。
- 未配置真实 embedding 时记录 `skipped: credentials not configured`。
- `rerank.backend=disabled` 时记录 `skipped: rerank disabled by config`。

失败处理：

- rebuild 后仍返回已删除记录：记录为 Pilot blocker。
- embedding provider 失败：记录 endpoint host、model、dimensions 和错误摘要，不记录 API key。

## 14. 汇总判定

根据 [pilot-acceptance-guide.md](pilot-acceptance-guide.md) 的标准做最终判定。

Go：

- 配置、SQLite backup / upgrade / restore drill、服务启动、health check、CLI、observability、diagnostics、
  memory、long-term context、reflection、KB local、vector reindex 全部通过。
- 真实外部 smoke 至少 check 通过，或明确记录为 `skipped`。

Conditional Go：

- 核心本地链路通过。
- 真实 LLM、embedding、Google Drive 或 Confluence 因凭据、网络、scope 或测试数据问题失败。
- 报告中记录 workaround、owner 和复测时间。

No-Go：

- 配置加载、服务启动、DB migration、backup / restore、diagnostics、observability 查询、memory 基础链路、
  KB local 或 vector reindex 任一不可用。
- 发现 secret 泄漏到配置、日志、trace、diagnostics package 或 issue。

## 15. 常见失败定位顺序

服务无法启动：

1. 检查 `config/settings.yaml`。
2. 检查 `database_url` 和 DB 文件权限。
3. 检查 `uv run alembic upgrade head`。
4. 检查启动日志是否包含 import error 或配置错误。

CLI 命令不可用：

1. 运行 `uv sync --frozen --group dev`。
2. 运行 `uv run fleetent-admin --help`。
3. 检查 `pyproject.toml` 的 `[project.scripts]`。
4. 本地 `.venv` 异常时删除 `.venv` 后重建。

KB connector 失败：

1. 先跑 `kb connectors check`。
2. 再跑 `sync --dry-run`。
3. 只在 opt-in 和凭据完整时跑真实 sync。
4. 记录 connector status，不把 token 或文档正文写进 issue。

验收报告无法下结论：

1. 先确认核心本地链路是否全部通过。
2. 再确认失败项是否只属于真实外部 smoke。
3. 把问题分类为 `pilot_blocker`、`docs_gap`、`enhancement` 或 `out_of_scope`。
4. 对 blocker 安排修复和复测；对 Conditional Go 项写清 owner 和复测时间。
