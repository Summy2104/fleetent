# Pilot 部署与人工验收 Runbook

本 runbook 面向第一次 Pilot 测试环境部署和验收。它不是自动化测试清单，而是给 operator、实施人员和
模块 owner 使用的人工验收手册：每一步都说明要证明什么能力、模拟什么场景、应该看到什么证据，以及失败时
如何分类。

Pilot 默认部署入口是 Docker Compose；源码环境下的 `uv run uvicorn fleetent.server:app` 只作为开发模式。

相关文档：

- [pilot-install-checklist.md](pilot-install-checklist.md)：安装、升级、备份和回滚清单。
- [pilot-acceptance-guide.md](pilot-acceptance-guide.md)：验收标准、外部 smoke 状态和报告模板。

自动化证据入口：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

该命令输出 `pilot-capability-verification.md` 和 `pilot-capability-verification.json`。人工验收时先查看
Markdown，再把 JSON 作为可追踪附件保存。真实 smoke 默认关闭；只有显式设置 `FLEETENT_REAL_LLM_SMOKE=1`、
`FLEETENT_GOOGLE_DRIVE_SMOKE=1` 等 opt-in flag，并配置对应 credential ref 后才运行真实外部依赖。报告
会把问题归入 `Pilot blocker`、Docs gap、Enhancement 或 Out-of-scope，并给出 Go / `Conditional Go` /
No-Go 建议；最终判定仍由 operator 和 owner 复核。

轻量门禁与手动维护边界：

```bash
uv run fleetent-admin validate-config --profile pilot --format json
uv run python scripts/generate_pilot_verification_report.py
```

- `validate-config` 先检查 DB URL、data/config/secrets 目录、生产依赖、connector credential ref 和配置文件中的
  inline secret-like 值；通过环境变量或受控 secret 文件注入的真实 token 不作为 inline config secret 失败。
- diagnostics package 不包含 SQLite 主库、备份、secret 文件、完整 prompt/reply 或 KB document body；只保存
  脱敏 summary、manifest、connector status 和 skip reason。
- KB connector real smoke 默认只允许 check + dry-run；execute sync 必须额外 opt-in，且只允许 Pilot fixture 目录或空间。
- maintenance 命令必须先 dry-run；apply / rebuild / delete / approve / reject 必须带 --yes，并记录 audit 或
  trace 凭证。

执行原则：

- 先证明核心本地链路，再检查真实外部依赖。
- 真实 LLM、embedding、Google Drive、Confluence 和 rerank smoke 都必须显式 opt-in。
- 未配置凭据的真实外部 smoke 记录为 `skipped: credentials not configured`，不默认判失败。
- 自动化测试只能作为辅助证据；人工验收必须记录可观察现象，例如 CLI 输出、HTTP 状态、trace 事件、
  source attribution、diagnostics manifest 或 connector status。
- 任何输出、报告、issue 和 diagnostics package 都不得包含真实 secret、token、credential payload、
  完整 prompt / reply、KB 文档正文、SQLite 主库或 SQLite backups。

## 0. 准备验收记录

验收目标：

- 建立一份可追踪的验收记录，后续每个模块都能回到同一份报告。
- 避免最后只知道“跑过测试”，但不知道哪个环境、哪个版本、哪些外部依赖被跳过。

记录模板：

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
  core_checks:
  external_smoke:
  issues:
  accepted_risks:
  final_decision:
```

应该看到什么：

- 报告里有环境名称、operator、branch、commit SHA、开始时间和数据目录。
- 每个后续模块都能填入 `passed`、`failed` 或 `skipped`，并附一条脱敏证据。

失败判断：

- 无法确认版本或环境：停止验收，不能进入真实外部 smoke。
- 测试数据来源不清楚：先确认数据 owner 和脱敏策略。

## 1. 确认代码版本和工作区

验收目标：

- 证明部署的是可追踪版本。
- 证明没有误把 secret、DB、backup 或 diagnostics package 带进 git。

操作步骤：

```bash
git rev-parse --abbrev-ref HEAD
git rev-parse HEAD
git status --short
```

应该看到什么：

- branch 和 commit SHA 与验收记录一致。
- `git status --short` 不显示 `.env`、credential 文件、`data/`、SQLite DB、backup 或 diagnostics package。

通过标准：

- 工作区没有未解释的改动。
- 如果有部署环境本地配置文件，它们不在 git 跟踪范围内。

失败判断：

- 出现 secret 或 data 文件：部署准备失败，先清理并检查 `.gitignore`。
- 出现未提交业务改动：记录来源；无法确认来源时停止验收。

## 2. 准备配置和 Secret

验收目标：

- 证明配置文件只保存非敏感策略。
- 证明真实凭据由环境变量或受控 secret 文件提供。
- 证明 agent 运行配置和 MCP servers 均只保存非敏感引用。

操作步骤：

```bash
test -f config/agent.yaml
```

人工检查：

- `config/agent.yaml` 里只有 agent、model、MCP server、knowledge base、connector、provider 等非敏感配置。
- Google Drive / Confluence credential 使用平铺的 `*_env` 引用，例如
  `FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`、`FLEETENT_CONFLUENCE_TOKEN`。
- MCP server API key 也只使用 `api_key_env` 等环境变量名引用，不保存 token payload。
- 环境变量或受控 secret 文件的权限由部署方保护。

应该看到什么：

- 配置文件可读取。
- 验收记录只写 credential ref，不写 credential 内容。

失败判断：

- 配置文件包含真实 token：记录为 No-Go 候选。
- credential_ref 指向文件不存在或权限过宽：记录为配置问题，修正后复测。

## 3. 安装依赖和确认 CLI

验收目标：

- 证明项目依赖可安装。
- 证明用户入口 `fleetent` 和管理入口 `fleetent-admin` 都可执行。

操作步骤：

```bash
docker compose build fleetent
docker compose run --rm fleetent uv run fleetent --help
docker compose run --rm fleetent uv run fleetent-admin --help
docker compose run --rm fleetent uv run fleetent-admin init-config
```

应该看到什么：

- 镜像构建成功。
- `fleetent --help` 能显示 agent CLI 用法。
- `fleetent-admin --help` 能显示管理命令。
- `.env`、`config/agent.yaml`、`data/`、`data/logs/`、
  `data/diagnostics/` 和 `secrets/` 已初始化；如果文件已存在，命令会跳过。

失败判断：

- 镜像构建失败：检查 Dockerfile、`uv.lock` 和网络代理。
- `uv run` 找不到命令：检查镜像内 `pyproject.toml` 的 `[project.scripts]` 和 lock 文件。
- 这一步失败属于部署 blocker，因为后续验收无法执行。

## 4. SQLite 升级、备份和恢复点

验收目标：

- 证明 migration 前有 SQLite backup。
- 证明 backup 失败时不会继续 migration。
- 证明 migration 失败时保留恢复点。

操作步骤：

```bash
docker compose run --rm fleetent uv run python scripts/upgrade.py --dry-run
docker compose run --rm fleetent uv run python scripts/upgrade.py --backup-only
docker compose run --rm fleetent uv run python scripts/upgrade.py
```

应该看到什么：

- dry-run 输出 database URL、backup 路径和 migration 计划。
- dry-run 不创建 backup，也不运行 Alembic。
- backup-only 创建 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`，不运行 migration。
- upgrade 在 backup 成功后运行 `alembic upgrade head`。
- 验收记录写入 backup 路径和 migration 结果。

通过标准：

- backup 文件存在。
- migration 成功。
- migration 后服务仍可启动。

失败判断：

- DB 文件不存在且不是 dry-run：部署准备失败。
- backup 失败：不要运行 migration。
- migration 失败：保留 backup，记录 Alembic 错误摘要和 backup 路径。

## 5. 启动服务和基础 Health Check

验收目标：

- 证明服务可以启动。
- 证明 HTTP health、admin CLI 和一次最小 agent run 可用。

操作步骤：

启动服务：

```bash
docker compose up -d
```

另开终端检查：

```bash
curl -fsS http://127.0.0.1:8765/health
uv run fleetent-admin observability traces --limit 5
uv run fleetent "hello"
```

`uv run uvicorn fleetent.server:app` 只作为开发模式保留，不作为 Pilot 默认部署入口。

应该看到什么：

- 服务启动日志无配置错误、DB migration 错误或 secret 打印。
- `/health` 返回 200。
- `fleetent-admin observability traces --limit 5` 可执行。
- `fleetent "hello"` 产生一次可追踪 run；如果真实 LLM 未配置，应明确记录 `skipped` 或 `failed`。

通过标准：

- 服务可启动且 health check 通过。
- 最小 CLI run 的结果能在 observability 中定位到。

失败判断：

- 服务无法启动：先检查配置加载、database URL、migration 状态和 import error。
- `/health` 非 200：记录 HTTP 状态、错误摘要和服务日志路径。
- CLI agent 失败：区分 provider 未配置、网络问题和 runtime 错误。

## 6. Observability 和 Diagnostics

验收目标：

- 证明 operator 能定位一次测试 run。
- 证明 usage 和 performance 能支持排查。
- 证明 diagnostics package 可导出且脱敏。

用户场景：

- operator 接到“Agent 没有正确回答”或“connector 同步失败”的反馈，需要用 trace、usage、
  performance 和 diagnostics 定位问题，但不能泄漏用户正文或凭据。

操作步骤：

1. 先执行一次最小 agent run，或选择本次验收中的任一测试 run。
2. 查询 trace、usage、performance。
3. 导出 diagnostics package。
4. 检查 diagnostics manifest 和内容边界。

命令：

```bash
uv run fleetent-admin observability traces --limit 20
uv run fleetent-admin observability traces --event-type agent_run_failed --limit 50
uv run fleetent-admin observability usage --limit 100
uv run fleetent-admin observability performance --limit 100
uv run fleetent-admin diagnostics export
uv run fleetent-admin diagnostics retention dry-run
```

应该看到什么：

- traces 里能看到 run id、event type、时间、状态和 payload key summary。
- usage 里能看到 run count、token usage 和 by-model summary。
- performance 里能看到失败率、延迟、LLM / tool / fallback / permission 指标。
- diagnostics package 包含 manifest、logs、trace / usage / performance 摘要、connector status、
  environment 和 config summary。
- diagnostics package 不包含 prompt、reply、tool payload、memory 内容、KB 文档正文 / chunks、
  SQLite 主库、SQLite backups 或 credential 文件内容。

通过标准：

- operator 能用 trace 定位一次 run。
- usage 和 performance 输出能支持问题排查。
- diagnostics 脱敏边界符合要求。

失败判断：

- trace / usage / performance 不可查询：Pilot blocker 候选。
- diagnostics 泄漏 secret 或业务正文：No-Go。
- retention dry-run 删除或修改数据：No-Go。

## 7. Memory 场景验收

验收目标：

- 证明 User Memory 能从交互中产生，并在后续交互中被利用。
- 证明 User Memory 归属于用户，不会误进入 KB 或 tenant 级共享记忆。
- 证明 maintenance 只生成候选，不自动改写用户记忆。

用户场景：

- 用户告诉 Agent：“我负责美国客户的知识库模块，平时优先关注 Google Drive 和 Confluence。”
- 用户开启新问题：“我负责哪些模块？我应该优先验收哪些 connector？”
- Agent 应能利用之前记录的 User Memory 给出相关回答。

准备数据：

- 一个测试 user id。
- 一轮包含用户职责、偏好或长期背景的测试对话。
- 一轮后续查询，用于触发 memory search 和 context injection。

操作步骤：

1. 用测试 user id 发起第一轮对话，输入用户职责或偏好。
2. 发起第二轮对话，询问与第一轮信息相关的问题。
3. 查询 observability trace，确认出现 memory search / context injection 相关事件。
4. 运行 memory maintenance dry-run，确认只生成候选。

应该看到什么：

- Agent 的第二轮回答能利用第一轮信息，而不是只基于当前问题。
- trace 中能看到 memory 被搜索或注入的证据。
- memory 记录与测试 user id 绑定。
- maintenance dry-run 输出候选，不直接删除、合并或改写 memory。

通过标准：

- User Memory 能写入、检索和注入。
- memory owner 边界正确。
- maintenance 默认不自动 apply。

失败判断：

- Agent 回答没有利用历史信息：检查 memory extraction、search 和 context injection。
- memory 进入 KB 或跨用户可见：No-Go。
- maintenance 自动改写 memory：Pilot blocker。

辅助自动化：

```bash
uv run pytest tests/evaluation/test_memory_extraction_eval.py -q
```

这条命令只能证明 deterministic fixture 通过，不能替代上述人工场景验收。

## 8. Long-term Context 场景验收

验收目标：

- 证明长期上下文可以同时利用 User Memory 和 KB。
- 证明 source attribution 可追踪。
- 证明 token budget 限制生效。

用户场景：

- 用户已经有一条 User Memory：“我负责美国客户的知识库模块。”
- KB local source 中有一份测试文档，描述 Google Drive connector 的验收步骤。
- 用户询问：“我验收 Google Drive connector 时应该重点看什么？”

准备数据：

- 一条与测试 user id 绑定的 User Memory。
- 一个已同步的 KB local source。
- 一个会同时命中 memory 和 KB 的测试问题。

操作步骤：

1. 确认 User Memory 存在。
2. 同步 KB local source。
3. 发起测试问题。
4. 查询 trace，查看 context injection 和 source attribution。
5. 降低 token budget 后复测。
6. 暂时禁用或清空 KB 后复测。

应该看到什么：

- 回答能结合用户职责和 KB 文档内容。
- trace 里能看到 memory source 和 knowledge source attribution。
- 降低 token budget 后，注入内容减少，并记录 budget decision。
- KB 不可用时，memory 仍可注入，不导致整体失败。

通过标准：

- memory 和 KB 都能参与长期上下文。
- attribution 可追踪。
- budget policy 可观察。
- KB 缺失不阻塞 memory 注入。

失败判断：

- attribution 缺失：检查 query trace 和 long-term context 事件。
- budget 不生效：记录配置值、输入长度和实际注入长度。
- KB 缺失导致 memory 也不可用：Pilot blocker 候选。

辅助自动化：

```bash
uv run pytest tests/evaluation/test_long_term_context_eval.py -q
```

## 9. Reflection 场景验收

验收目标：

- 证明 reflection 能基于 trace 生成报告。
- 证明报告有 evidence ids，而不是只给主观结论。
- 证明 memory 相关建议进入 pending proposal，不自动改写 User Memory。

用户场景：

- 最近一段测试中，用户多次提到职责变化或偏好冲突。
- reflection 需要发现“可能需要更新 User Memory”的候选项。
- operator 或用户后续可以审核这些候选，而不是系统自动修改。

准备数据：

- 最近 7 天内的测试 trace。
- 至少一个 memory_candidate 或 memory_conflict 场景。

操作步骤：

1. 选择本次验收产生的测试 trace。
2. 运行 reflection report smoke。
3. 查看 report 的 finding type、summary、evidence ids 和 metadata。
4. 查看是否生成 User Memory maintenance proposals。
5. 确认 proposals 默认 pending。

应该看到什么：

- report 指向具体 evidence ids。
- report 不保存完整 transcript。
- memory_candidate / memory_conflict 生成 pending proposal。
- `suggest_shared_memory_or_kb` 不写 User Memory。

通过标准：

- reflection report 可生成。
- evidence 可追踪。
- memory 维护建议不会自动 apply。

失败判断：

- trace 不足：先补测试数据，不直接判断 finding 质量失败。
- report 无 evidence：功能缺口。
- proposal 自动 apply：Pilot blocker。

辅助自动化：

```bash
uv run pytest tests/evaluation/test_reflection_report_eval.py -q
```

## 10. Knowledge Base Local 场景验收

验收目标：

- 证明本地知识库 source 可以 plan、sync、search。
- 证明 dry-run 不写数据。
- 证明删除或修改源文件后可以 reingest / archive。
- 证明 KB scope 隔离生效。

用户场景：

- operator 准备一个测试目录，里面放一份“Google Drive connector 验收说明”文档。
- 用户向 Agent 提问：“Google Drive connector check 失败时应该看什么？”
- Agent 应能从该文档检索到相关 chunk，并带 source attribution。

准备数据：

- 一个测试 KB。
- 一个测试 local directory。
- 至少一份 `.txt`、`.md` 或 `.html` 文档。
- 一个会命中文档内容的问题。

操作步骤：

1. 创建或确认测试 KB。
2. 配置 local source 指向测试目录。
3. 运行 sync dry-run，查看 new / changed / unchanged / missing 动作。
4. 执行 sync。
5. 发起 KB search 或通过 Agent 查询。
6. 修改源文件后再次 dry-run，观察 reingest 计划。
7. 删除源文件后再次 dry-run，观察 archive 计划。

应该看到什么：

- dry-run 输出计划，但不写 KB、source state 或 vector index。
- sync 后 search 能返回相关 chunk。
- 回答或 trace 中能看到 source attribution。
- 修改源文件后计划 reingest。
- 删除源文件后计划 archive，reindex 后不再返回旧 chunk。
- 未绑定 KB 或不在 scope 内的内容不会被返回。

通过标准：

- local source 可 sync 和 search。
- plan / execute 分离。
- scope 隔离生效。
- source 删除后旧内容不会继续污染结果。

失败判断：

- dry-run 写数据：Pilot blocker。
- search 返回越权内容：No-Go。
- 删除源文件后仍返回旧 chunk：vector reindex 或 archive 缺口。

辅助自动化：

```bash
uv run pytest tests/evaluation -x -q
```

## 11. Google Drive Connector 场景验收

验收目标：

- 证明 Google Drive connector 配置可检查。
- 证明真实同步只有在显式 opt-in 和凭据完整时才运行。
- 证明失败原因可被 operator 理解，而不是只看到异常堆栈。

用户场景：

- 企业将某个 Google Drive folder 作为部门知识库来源。
- operator 需要确认 connector 能访问该 folder，能 dry-run，同步后能查询，且不会泄漏 OAuth token。

准备数据：

- 一个测试 Google Drive folder。
- 一个 connector id。
- `credential_ref`，例如环境变量或受控 token 文件。
- 一份测试文档，内容不要包含真实客户敏感数据。

操作步骤：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <google_drive_connector_id>
uv run fleetent-admin kb connectors sync <google_drive_connector_id> --dry-run
uv run fleetent-admin kb connectors status <google_drive_connector_id>
```

如需真实 sync：

```bash
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  uv run fleetent-admin kb connectors sync <google_drive_connector_id> --yes --pilot-fixture
```

应该看到什么：

- list 输出 connector id、type、tenant、KB 和 scope，不输出 credential payload。
- check 返回 `ok`，或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、`scope_unreachable`。
- dry-run 不写 KB、source state 或 vector index。
- 真实 sync 成功后，status 显示最近一次同步结果和脱敏摘要。
- 同步后的测试文档可通过 KB search 或 Agent 查询命中。

通过标准：

- check 结果明确。
- dry-run 安全。
- execute opt-in、`--yes` 和 `--pilot-fixture` 齐全后真实 sync 可执行，或因凭据未配置被明确记录为 skipped。
- 输出不包含 OAuth token 或 credential payload。

失败判断：

- 凭据未配置：记录 `skipped: credentials not configured`。
- check 失败：记录状态、connector id、scope 和脱敏错误摘要。
- sync 失败但核心本地 KB 链路正常：Conditional Go 候选。
- 输出泄漏 token：No-Go。

## 12. Confluence Connector 场景验收

验收目标：

- 证明 Confluence connector 配置可检查。
- 证明 space / page scope 可验证。
- 证明真实同步输出脱敏。

用户场景：

- 企业将某个 Confluence space 或 page tree 作为知识库来源。
- operator 需要确认 connector 能访问 scope，dry-run 不写数据，真实 sync 后可查询测试页面。

准备数据：

- 一个测试 Confluence space 或 page。
- 一个 connector id。
- base URL、username、credential_ref 和 scope。
- 一页测试内容，不包含真实客户敏感数据。

操作步骤：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <confluence_connector_id>
uv run fleetent-admin kb connectors sync <confluence_connector_id> --dry-run
uv run fleetent-admin kb connectors status <confluence_connector_id>
```

如需真实 sync：

```bash
FLEETENT_CONFLUENCE_EXECUTE_SYNC=1 \
  uv run fleetent-admin kb connectors sync <confluence_connector_id> --yes --pilot-fixture
```

应该看到什么：

- check 返回 `ok`，或明确的 `credential_missing`、`credential_invalid`、`auth_failed`、`scope_unreachable`。
- dry-run 不写 KB、source state 或 vector index。
- 真实 sync 成功后，status 显示同步结果和脱敏摘要。
- 同步后的测试页面可被 KB search 或 Agent 查询命中。
- 输出不包含 API token、credential payload 或页面正文。

通过标准：

- check 结果明确。
- dry-run 安全。
- opt-in 后真实 sync 可执行，或因凭据未配置被明确记录为 skipped。
- 输出脱敏。

失败判断：

- 凭据未配置：记录 `skipped: credentials not configured`。
- scope 无法访问：记录 space / page scope 的脱敏标识和错误摘要。
- 输出泄漏 token 或页面正文：No-Go。

## 13. Vector Store / Embedding / Rerank 场景验收

验收目标：

- 证明 vector index 可以从 source of truth 重建。
- 证明删除的 memory 或 KB chunk 不会长期污染搜索结果。
- 证明真实 embedding provider smoke 可选且脱敏。
- 证明 rerank 未启用时不会误判为 blocker。

用户场景：

- operator 更换 embedding 模型或重建索引。
- 系统需要从 User Memory 和 KB chunks 重新生成索引。
- 删除过的 source 不应继续出现在搜索结果里。

准备数据：

- 至少一条 User Memory。
- 至少一个 KB chunk。
- 一条随后被删除或 archive 的 source record。

操作步骤：

1. 对 memory namespace 执行 reindex dry-run，确认枚举 User Memory source of truth。
2. 对 KB namespace 执行 reindex dry-run，确认枚举 KB chunks source of truth。
3. 执行 rebuild。
4. 运行 search，确认返回当前记录。
5. 删除或 archive source record。
6. 再次 rebuild。
7. 再次 search，确认旧记录不再返回。

真实 embedding smoke：

```bash
FLEETENT_EVAL_REAL_EMBEDDING=1 uv run pytest tests/evaluation -k embedding -q
```

应该看到什么：

- dry-run 列出待重建记录，不写 index。
- rebuild 后 search 结果与 source of truth 一致。
- 删除或 archive 后，旧内容不再返回。
- 未配置真实 embedding 时记录 `skipped: credentials not configured`。
- `rerank.backend=disabled` 时记录 `skipped: rerank disabled by config`。

通过标准：

- index 可重建。
- search 不返回已删除 source。
- embedding provider 失败时有脱敏错误摘要。
- rerank disabled 不阻塞 Pilot。

失败判断：

- rebuild 后仍返回已删除记录：Pilot blocker。
- embedding provider 失败：记录 endpoint host、model、dimensions 和错误摘要，不记录 API key。
- rerank 被禁用但文档要求它必须通过：文档判断错误，按 docs gap 处理。

辅助自动化：

```bash
uv run pytest tests/evaluation -x -q
```

## 14. 汇总判定

验收目标：

- 把每个模块的证据汇总成 Go、Conditional Go 或 No-Go。
- 明确哪些问题阻塞 Pilot，哪些是 docs gap、enhancement 或 out-of-scope。

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

问题分类：

```text
issue_id:
title:
category: pilot_blocker | docs_gap | enhancement | out_of_scope
status: open | fixed | accepted_risk | deferred
severity: critical | high | medium | low
owner:
command_or_step:
expected:
actual:
sanitized_evidence:
workaround:
go_impact: go | conditional_go | no_go
retest_command:
retest_result:
```

## 15. 常见失败定位顺序

服务无法启动：

1. 检查 `config/agent.yaml` 和 `.env`。
2. 检查 `database_url` 和 DB 文件权限。
3. 检查 `uv run alembic upgrade head`。
4. 检查启动日志是否包含 import error 或配置错误。

CLI 命令不可用：

1. 运行 `docker compose build fleetent`。
2. 运行 `docker compose run --rm fleetent uv run fleetent-admin --help`。
3. 检查 `pyproject.toml` 的 `[project.scripts]`。
4. 如镜像缓存异常，重新构建镜像后复测。

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
