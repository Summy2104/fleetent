# Intelligence Roadmap 人工测试手册

本手册用于把 [intelligence-roadmap.md](../capabilities/roadmaps/intelligence-roadmap.md)
从“本地自动化已通过”推进到 Pilot `Go` 所需的人工证据。它只覆盖 Memory、Long-term Context、
Reflection、Vector Store 和 Knowledge Base；部署、诊断包和配置检查见
[observability-deployment-roadmap-test-manual.md](observability-deployment-roadmap-test-manual.md)。

## 1. Go 判定边界

达到 `Go` 需要同时满足：

- 默认自动化测试通过，且 skipped 项均有明确原因。
- Memory / Long-term Context / Reflection / Vector Store / Knowledge Base 的本地链路可由 operator 复核。
- 真实 LLM、embedding、rerank、Google Drive、Confluence smoke 均记录为 `passed`，或由 Pilot owner 明确接受为不阻塞的 `skipped`。
- 所有真实外部 smoke 输出都不包含 secret、credential payload、完整 prompt / reply 或 KB 文档正文。
- 失败项已按 `Pilot blocker`、Docs gap、Enhancement、Out-of-scope 分类，并有 owner、workaround 和复测时间。

`Go` 不是要求每个增强能力都有 UI；review UI、scheduler、full sync history、document-level ACL、OCR / VLM
仍可作为 Enhancement 进入后续 roadmap。

## 2. 前置条件

本机作为服务器：

- 可以把当前机器当作单节点准生产环境完成本手册的大部分人工验证。
- 推荐仍使用 Docker Compose 路径启动服务；源码环境下的 `uv run uvicorn fleetent.server:app --reload`
  只作为开发模式补充证据。
- 本机模式可以验证 Memory、Long-term Context、Reflection、Vector Store、local KB、真实 provider 出站调用、
  Google Drive / Confluence connector check 和 sync。
- 本机模式不能替代客户网络、企业 IdP、真实 IM 入站公网回调、多节点部署、生产权限审批和长期稳定性验证。
- 如果需要验证 Slack / Telegram / webhook 入站，本机必须配置受控 tunnel 或可访问的回调地址；否则记录为
  `skipped: local server has no public inbound route`，并交由 Platform / Channel 验收处理。

记录环境：

```text
environment:
  name: local-as-server
  operator:
  branch:
  commit_sha:
  started_at:
  data_dir:
  config_dir:
```

准备测试数据：

- 一个测试用户，例如 `pilot-user-memory`。
- 一个测试 tenant，例如 `pilot-tenant`。
- 一个测试 team，例如 `pilot-team`。
- 一个本地 KB fixture 目录，包含 Markdown / text / PDF / DOCX / PPTX / XLSX 中至少两类文件。
- 一个 Google Drive Pilot fixture folder，只放脱敏文档。
- 一个 Confluence Pilot fixture space 或 page scope，只放脱敏页面。

真实外部依赖 opt-in 变量按需设置。真实 provider credential 只能放在本机 shell、未跟踪的 `.env`
或 `secrets/` 文件中，不要写入本手册、验收记录、测试 fixture、commit、issue、日志或 trace。运行命令前只记录
使用了哪个 provider 和 credential 来源类型，例如 `env:ANTHROPIC_API_KEY` 或 `file:///app/secrets/...`，不要记录值。

Real LLM memory extraction evaluation 是显式 opt-in；默认门禁不会调用真实模型。该评测在本模块使用
`FLEETENT_EVAL_MEMORY_LLM_API_KEY` 作为凭据变量，并受 `FLEETENT_EVAL_REAL_LLM` 控制。需要本机先设置：

```bash
export FLEETENT_EVAL_MEMORY_LLM_API_KEY=<provider api key>
export FLEETENT_EVAL_REAL_LLM=1
uv run pytest tests/evaluation/test_memory_extraction_eval.py -q -rs
```

如果 opt-in 后缺少 `FLEETENT_EVAL_MEMORY_LLM_API_KEY`，测试应跳过并给出需要配置真实 credential 的原因；如果
provider key 无效，
记录为失败并由 operator 更换或撤销 credential。不要用 `env`、`set -x`、完整 shell transcript 或 diagnostics
package 打印 secret。

Runtime/Provider 级真实 smoke 按需设置 opt-in flag，并通过 credential reference 指向本机 secret：

```bash
export FLEETENT_REAL_LLM_SMOKE=1
# 预先在本机 shell 或未跟踪 .env 中提供 ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY。

export FLEETENT_REAL_EMBEDDING_SMOKE=1
export FLEETENT_REAL_EMBEDDING_CREDENTIAL_REF=file:///app/secrets/embedding-provider-token

export FLEETENT_REAL_RERANK_SMOKE=1
export FLEETENT_REAL_RERANK_CREDENTIAL_REF=file:///app/secrets/rerank-provider-token

export FLEETENT_GOOGLE_DRIVE_SMOKE=1
export FLEETENT_GOOGLE_DRIVE_CREDENTIAL_REF=file:///app/secrets/google-drive-token.json
export FLEETENT_GOOGLE_DRIVE_FOLDER_ID=<pilot_fixture_folder_id>

export FLEETENT_CONFLUENCE_SMOKE=1
export FLEETENT_CONFLUENCE_BASE_URL=<confluence_base_url>
export FLEETENT_CONFLUENCE_USERNAME=<pilot_user_email>
export FLEETENT_CONFLUENCE_CREDENTIAL_REF=env:FLEETENT_CONFLUENCE_TOKEN
export FLEETENT_CONFLUENCE_SCOPE=<pilot_space_or_page_scope>
```

## 3. 自动化快验

先跑默认门禁：

```bash
uv run pytest tests/integration/test_shared_memory.py \
  tests/integration/test_long_term_context_runtime.py \
  tests/integration/test_reflection.py \
  tests/integration/test_kb_reflection_reports.py \
  tests/integration/test_reflection_trend_summary.py \
  tests/integration/test_vector_store.py \
  tests/integration/test_vector_store_reindex.py \
  tests/integration/test_rerank_providers.py \
  tests/integration/test_knowledge_base.py \
  tests/integration/test_knowledge_base_sync_planner.py \
  tests/integration/test_knowledge_connector_operations.py \
  tests/evaluation/test_memory_extraction_eval.py \
  tests/evaluation/test_knowledge_base_retrieval_eval.py \
  tests/evaluation/test_long_term_context_eval.py \
  tests/evaluation/test_reflection_report_eval.py \
  tests/evaluation/test_knowledge_base_rerank_eval.py \
  -q
```

通过标准：

- 所有非真实外部依赖测试通过。
- skipped 项只来自显式 opt-in 的真实 provider / SaaS smoke。
- skipped 原因写入验收记录。

## 4. Memory 验收

目标：

- User Memory 可写入、检索、更新、删除或标记 stale。
- Shared Memory 可按 tenant / team scope 隔离。
- Memory maintenance proposal 不会未经 owner 批准自动改写 User Memory。

建议操作：

```bash
uv run fleetent-admin memory shared list --scope-type tenant --scope-id pilot-tenant
uv run fleetent-admin memory shared list --scope-type team --scope-id pilot-team
uv run pytest tests/integration/test_shared_memory.py tests/integration/test_memory_retention_compaction.py -q
```

人工复核：

- 查询结果只显示目标 tenant / team 的 Shared Memory。
- 验收记录中保存 memory item id、scope、status，不保存完整用户对话。
- maintenance proposal 初始为 pending；apply / reject 必须有 owner 操作记录。

失败分类：

- 跨用户、跨 tenant 或跨 team 泄漏：`Pilot blocker`。
- CLI 输出缺少足够定位信息但功能可用：Docs gap。
- 缺 review UI：Enhancement。

## 5. Long-term Context 验收

目标：

- Long-term Context 能同时使用 User Memory、Shared Memory 和 KB。
- context source attribution 可查询。
- Shared Memory scope 只能由 agent tenant / team ownership 派生。

建议操作：

```bash
uv run pytest tests/integration/test_long_term_context_runtime.py \
  tests/integration/test_long_term_ctx_policy_store.py \
  tests/evaluation/test_long_term_context_eval.py \
  -q
```

人工复核：

- 选择一次测试 run，记录 run id。
- 查询 trace，确认有 memory source、knowledge source 或 context budget decision。
- 确认没有任意跨 tenant / team scope 注入。

失败分类：

- attribution 缺失导致 operator 无法解释回答来源：`Pilot blocker` 候选。
- policy 可用但只能通过底层命令操作：Docs gap 或 Enhancement，按是否阻塞 Pilot 判定。

## 6. Reflection 验收

目标：

- Reflection 能基于 trace / memory / KB signals 生成只读报告。
- User Memory maintenance proposal、KB reflection report 和 SkillProposal 不会自动修改 Memory / KB / Skill。
- trend summary 只读聚合，不暴露完整 transcript 或 evidence payload。

建议操作：

```bash
uv run pytest tests/integration/test_reflection.py \
  tests/integration/test_kb_reflection_reports.py \
  tests/integration/test_skill_reflection_proposals.py \
  tests/integration/test_reflection_trend_summary.py \
  tests/evaluation/test_reflection_report_eval.py \
  -q
```

人工复核：

- 抽查一份 reflection report，记录 report id、finding type、evidence id。
- 确认 report 不保存完整 transcript。
- 确认 proposals 为 pending 或 owner-reviewed 状态，不自动 apply。

失败分类：

- report 泄漏完整 transcript、secret 或 KB 正文：No-Go。
- report 无 evidence id：`Pilot blocker` 候选。
- 缺 review UI 或 scheduler：Enhancement。

## 7. Knowledge Base Local 验收

目标：

- Local ingest、parser registry、chunking、hybrid search、graph search、query planner 可用。
- KB source attribution 可用于解释回答。
- agent 到多 KB binding 不越权。

建议操作：

```bash
uv run pytest tests/integration/test_knowledge_base.py \
  tests/integration/test_knowledge_base_local_connectors.py \
  tests/integration/test_knowledge_base_sync_planner.py \
  tests/integration/test_knowledge_search_planner.py \
  tests/integration/test_knowledge_base_graph_search.py \
  -q
```

人工复核：

- 使用脱敏 fixture 目录执行 local sync dry-run 和 apply。
- 搜索一个 fixture 中明确存在的问题，记录 query、top source ids、source attribution。
- 搜索一个不存在的问题，确认不会编造 source attribution。

失败分类：

- local ingest、search 或 source attribution 不可用：`Pilot blocker`。
- advanced parser 对某类文件失败但 text / Markdown 路径可用：Docs gap 或 Enhancement。

## 8. Google Drive Smoke

目标：

- Google Drive connector 可 list / check / dry-run sync / status。
- 真实 execute sync 只有在额外 opt-in 且使用 Pilot fixture folder 时执行。
- 输出只包含 connector id、scope、status、失败摘要和脱敏 source metadata。

建议操作：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <google_drive_connector_id>
uv run fleetent-admin kb connectors sync <google_drive_connector_id> --dry-run
uv run fleetent-admin kb connectors status <google_drive_connector_id>
```

真实 execute sync：

```bash
FLEETENT_GOOGLE_DRIVE_EXECUTE_SYNC=1 \
  uv run fleetent-admin kb connectors sync <google_drive_connector_id> --yes --pilot-fixture
```

通过标准：

- check 通过或失败原因明确。
- dry-run 给出 planned actions，不写入非预期数据。
- execute sync 只在 Pilot fixture folder 上运行。
- status 可查询最近一次 sync 结果。

失败分类：

- credential payload、token 或文档正文出现在输出中：No-Go。
- check 因网络或 scope 失败但本地 KB 可用：Conditional Go，记录 owner 和复测时间。
- connector 配置步骤不清楚：Docs gap。

## 9. Confluence Smoke

目标和判定与 Google Drive 相同，scope 使用 Pilot fixture space / page。

建议操作：

```bash
uv run fleetent-admin kb connectors list
uv run fleetent-admin kb connectors check <confluence_connector_id>
uv run fleetent-admin kb connectors sync <confluence_connector_id> --dry-run
uv run fleetent-admin kb connectors status <confluence_connector_id>
```

真实 execute sync：

```bash
FLEETENT_CONFLUENCE_EXECUTE_SYNC=1 \
  uv run fleetent-admin kb connectors sync <confluence_connector_id> --yes --pilot-fixture
```

通过标准：

- scope 明确限制到 Pilot space / page。
- 429 retry、失败摘要和 latest status 可观察。
- 输出不包含 API token、credential payload 或页面正文。

## 10. Vector Store / Embedding / Rerank 验收

目标：

- memory / KB index 可 dry-run reindex。
- embedding provider 可真实 smoke。
- rerank provider 可真实 smoke，且 KB hybrid rerank 显式 opt-in。

建议操作：

```bash
uv run pytest tests/integration/test_vector_store.py \
  tests/integration/test_vector_store_reindex.py \
  tests/integration/test_embedding_providers.py \
  tests/integration/test_rerank_providers.py \
  tests/evaluation/test_memory_kb_embedding_eval.py \
  tests/evaluation/test_knowledge_base_rerank_eval.py \
  -q
```

人工复核：

- 记录 memory namespace 和 KB namespace 的 dry-run reindex counts。
- 真实 embedding smoke 不记录 embedding vector 原始值。
- 真实 rerank smoke 记录 provider、query、candidate count、排序是否改变，不记录完整文档正文。

失败分类：

- reindex source of truth 不可枚举：`Pilot blocker`。
- 真实 provider 因凭据或网络失败：Conditional Go，记录 workaround。
- 真实 rerank 质量一般但 deterministic rerank 可用：Enhancement。
- 缺少真实 provider key：记录到人工复核清单，说明需要配置真实 credential 的原因。

## 11. 汇总到 Go 证据

生成报告：

```bash
uv run python scripts/generate_pilot_verification_report.py
```

验收记录模板：

```text
intelligence_acceptance:
  automated_tests:
    status:
    skipped:
  memory:
    status:
    evidence:
  long_term_context:
    status:
    evidence:
  reflection:
    status:
    evidence:
  knowledge_base_local:
    status:
    evidence:
  google_drive:
    status:
    evidence:
  confluence:
    status:
    evidence:
  vector_embedding_rerank:
    status:
    evidence:
  issues:
  decision:
```

`Go` 需要没有 unresolved `Pilot blocker`，且真实外部 smoke 的 `failed` 项已被 owner 复核为不阻塞或已修复复测。
