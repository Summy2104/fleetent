# finalize-agent-identity

> **Provisional · confidence 最低**：agent 身份模型迁移**阶段 5（收尾）**（依据 `docs/architecture/agent-identity-model.md`）。排在阶段 2/3/4 全部落地之后；本阶段最依赖前序状态，**其 spec deltas / 代码点 待 2/3/4 落地后 finalize-time 校准**（尤其 traces 列正名牵动的 observability 措辞）。

## Why

身份模型收尾，三件事一次做齐：① 把原"阶段 1"的 **`traces.agent_id` → `agent_name` 列正名**（纯 R2 美容合规：列本已存 slug，agent 侧不该出现叫 `agent_id` 的列）并入此阶段；② 固化**两个翻译边界**——materialize 写边界（id→把 name 盖到 agent 产物，多已如此、本阶段确认）、read-projection 读边界（平台读 agent 侧 name-keyed 数据时经 `agents` 解析 name→id）；③ 立**守护规则**锁住身份模型长期不漂移。

## What Changes

- **`traces.agent_id` → `agent_name`**（agent_state.db 嵌入式 Y `RENAME COLUMN`，append after 当前 Y 最大版本、不硬编码；内容已是 slug、不变）。同步：`TraceEvent` / `TraceQuery` 字段、`query_trace_events()` 参数、索引 `idx_traces_agent_ts`、消费方（`agent_observability`、`agent_statistics`）改名。
- **读边界固化**：platform read-projection / observability 读 agent 侧 traces/sessions（按 name）关联回平台 agent（按 id）时，经 `agents` 表做 name→id 解析（收口一处）。
- **写边界确认**：materialize 落 agent 产物时把 `agents.name` 盖到目录/agent.yaml/agent 侧 traces；平台 id 不泄漏到 agent 侧。
- **守护测试**：① 平台关系表（除 `agents`）无 agent name 列、agent 引用一律 `agent_id`；② agent 侧无 agent id 列/标识（含列名）；③ name↔id 翻译只在 materialize / read-projection 两处。
- **文档**：`data-model.md` §3.3 traces 列名更新；§2 / §6 补"两翻译边界 + 守护"；标 identity-model 阶段 5 收尾。

## Capabilities

### Modified Capabilities

- `observability`: `query_trace_events()` 及 trace event 的 agent 维度字段由 `agent_id` 更名为 `agent_name`（agent 侧存 slug；语义不变）
- `platform-read-projection`: 平台读 agent 侧 name-keyed 数据时 SHALL 经 `agents` 解析 name→id 关联平台 agent（读翻译边界）
- `plane-boundary-guardrails`: 新增 agent 标识键守护——平台关系表（除 agents）只用 agent_id、agent 侧只用 name、翻译仅在两边界

> finalize-time 还需校准：`agent-observability-view`（"aggregated by agent_id" 措辞）随 traces 字段更名同步——此条留待 propose 时补，因依赖前序最终列名。

## Impact

- **owning package**：`runtime`（agent_state_migrations traces 列改名）、`observability`（traces.py + 消费方）、`platform`（read-projection / materialize 边界 + 守护测试）
- **public API surface**：`TraceEvent` / `TraceQuery` 的 agent 字段更名（内部）；`query_trace_events()` 参数更名
- **owned tables**：`agent_state.db.traces` 列 `agent_id`→`agent_name`（嵌入式 Y）
- **cross-module dependencies**：不碰 agent 零 platform import；写/读翻译边界均在平台侧
- **migration / shim plan**：嵌入式 Y `RENAME COLUMN`（内容不变）；无数据回填
- **相邻切片**：依赖阶段 2/3/4 全落地；traces.py 若与彼时在跑的 trace 类 change 重叠，apply 时排序 + 冲突自检
