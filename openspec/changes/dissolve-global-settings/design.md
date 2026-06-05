## Context

阶段 2 后 runtime 不再回读 `Settings` 的 agent-runtime 字段(治理/部署/智能层),它们成为死代码。
平台 stores 仍用 `Settings(anthropic_api_key="").database_url` 取平台 authoring DB。`config_validation.py`
仍读 `Settings` 的 embedding/rerank/knowledge_base/database_url 做部署校验,并对 `Settings.model_dump()`
扫 inline secret。`default-agent` 的默认解析早已是 `bindings.default`(零 DB),仅 CLI `set-default-agent`
还写 `default_agent_name` 到 `settings.yaml`。

## Goals / Non-Goals

**Goals:**
- 删除 `Settings` 全部 agent-runtime 死字段、IM tokens、`default_agent_name`、`agent_budget_global_*`。
- `Settings` 收缩为平台精简集(database_url + 平台进程日志 + 平台密钥引用)。
- 智能层子模型类(`VectorStoreSettings` 等)保留供 `AgentFile` 复用,迁到中性归属。
- `config_validation` retarget 到 `agent.yaml`。
- `set-default-agent` CLI 作用于 agent.yaml `bindings.default`。

**Non-Goals:**
- 不改 runtime 读取逻辑(阶段 2 已完成)。
- 不动平台 authoring DB schema / Alembic。
- 不引新依赖。

## Decisions

### D1: 子模型类归属
`VectorStoreSettings`/`EmbeddingSettings`/`RerankSettings`/`LongTermContextSettings`/`KnowledgeBaseSettings`/
`McpServerSettings`/`ObservabilitySettings`/`DiagnosticsSettings`/`SchedulingSettings`/`WebhooksSettings`/
KB connector 子模型 被 `AgentFile` import 复用,不能随 `Settings` 字段删除而删。**决定**:这些类留在
`config.py`(作为独立 pydantic models),仅从 `Settings` 移除对应**字段**;`AgentFile` 的 import 不变。
理由:最小改动、不制造模块搬迁的连带 import 风暴。`config.py` 从此既放精简 `Settings` 也放共享子模型。

### D2: `database_url` 与平台 DB;平台无 API key
平台 stores 的 `Settings(...).database_url` 保留——这是**平台 authoring DB**,与 per-agent home 推导出的
运行时 DB(阶段 1 决策)是两套。**决定**:`database_url` 留在精简 `Settings`。
**平台不需要任何 API key**(用户拍板):`anthropic_api_key` 从 `Settings` **整个删除**(不是降级为 optional)。
平台不跑 agent loop、不调 LLM。agent 运行时的默认路由 key 由 `model_router` 经 route 的 `api_key_env`(env)
解析,属 agent-runtime 侧,与平台 `Settings` 无关。连带:平台 stores 现有的 `Settings(anthropic_api_key="")`
改为 `Settings()`;删 `anthropic_api_key` 后 `YAML_SECRET_FIELDS` 清空(`SecretRejectingYamlSettingsSource`
仍作空集安全网保留,守 `settings.yaml` 不放任何已知密钥字段)。

### D3: `config_validation` retarget
现读 `Settings` 字段 + 扫 `Settings.model_dump()`。**决定**:改为加载并校验当前/指定 agent 的 `agent.yaml`
(治理/部署/智能层 + connectors),inline-secret 扫描复用阶段 1 的 `_reject_inline_secrets` 同源逻辑或其抽取;
平台层 prerequisite(DB 可达)仍可从精简 `Settings` 校验。

### D4: `YAML_SECRET_FIELDS` 与 SecretRejecting
删除 IM tokens 后,`YAML_SECRET_FIELDS` 仅余 `anthropic_api_key`(若保留)。`SecretRejectingYamlSettingsSource`
继续守 `settings.yaml` 不放密钥。

### D4.1: 阶段 2 遗留的 Settings-fallback 分支(阶段 3 必须一并处理)
阶段 2 把 runtime/intelligence/deployment 切到"active_agent() 优先、Settings 回退"。删 Settings 字段前,
这些**回退分支**必须改为读 home-derived 默认或保留中性常量,否则删字段会破坏无 agent 态:
- loop.py `_resolve_budget_config`/`_resolve_loop_config`/`_resolve_guardrail_threshold`/
  `_resolve_parallel_max`/`_resolve_default_tool_timeout` 的 `Settings()` 回退分支。
- termination.py `_default_config`、budget.py `_grace_defaults`、context.py `_default_config` 的 Settings 分支。
- layered_budget.py `LayeredBudgetConfig.from_settings`(`from_governance` 已是主路径)。
- session/manager.py、skills/registry.py、model/provider_health.py、tools/{image_gen,vision}_client.py、
  observability/diagnostics.py `_default_diagnostics`、intelligence/long_term_ctx `_ltc_config`、
  knowledge_base `_kb_config`/`_rerank_config`、vector_store/runtime import 时 `_configure(Settings())`。
- sub_agent_lifecycle.py `resolve_timeout` 的 Settings 回退(阶段 2 有意保留)。
处理方式:这些字段删除后,回退改为各 dataclass 的字面默认(GovernanceConfig/AgentFile 已持有等价默认),
或为进程级单例保留一个中性默认常量。`database_url` 回退**保留**(平台 DB)。

### D5: 删除顺序与防回读
先确认(grep + 测试)无运行时 import 被删字段,再删。删字段后跑全量测试捕捉漏网回读。`agent_budget_global_*`
的删除与阶段 2 移除 global 聚合配套。

## Risks / Trade-offs

- [漏删/漏改某处仍 import 被删字段 → import error 或 AttributeError] → 删前 grep 全库确认无回读;删后全量
  pytest + mypy 兜底。阶段 2 task 7.3 已产出死字段清单作为依据。
- [`config_validation` retarget 改动面] → 该模块测试在 integration;retarget 后补 agent.yaml 校验用例。
- [外部部署仍用旧 settings.yaml 字段] → BREAKING,在 proposal/迁移说明列出迁移路径(字段 → agent.yaml)。

## Migration Plan

- BREAKING:旧 `settings.yaml` 的 agent-runtime namespace 失效。迁移:逐字段搬到对应 agent 的 `agent.yaml`
  (阶段 1 已支持承载)。`default_agent_name` → `bindings.default`;IM tokens → `connectors.*` 的 `*_env`。
- 平台 authoring DB(`database_url`)不变。
- 回滚:恢复 `Settings` 字段(git revert);因 runtime 已读 agent 配置,回滚仅恢复死字段,无数据影响。

## Open Questions

- 无阻塞性问题。(平台 API key 归属已定:整删,见 D2。)
