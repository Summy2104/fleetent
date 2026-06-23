## Why

KB 检索可观测/评估的两个 admin 端点是占位：`kb_observation` 返回硬编码 `{recall_hits:0,...}`、`kb_evaluation` 返回 `{metrics:{}, wired:False}`（注释明写 "Bridges the eval runner"）。③ kb-retrieval-audit 已落地、开始写 `kb_retrieval` trace——现在可以把这两个端点接上真实数据了。

关键判断（[[kb-production-gaps-plan]] #4，已定）：**线上算不出真 recall**（需 ground truth 标注）。所以分两端：
- `/observation` = **线上 proxy 指标**（从 ③ 的 trace 出延迟/空召回率/score 分布等），**不是真 recall**——现占位字段名 `recall_hits` 是陷阱。
- `/evaluations` = **离线在标注 fixture 上**算真 **recall@k / MRR**（fixture + 确定性 runner 已存在于 `tests/evaluation/`）。

> KB 生产化缺口 ④（车道 B）。依赖 ③(已落地)。**无迁移**、不碰 server.py/node/im——与在飞的 #4a(IM-edge)、#1(已落地) 零重叠。

## What Changes

- **`/observation` 接真实 proxy 指标**：聚合 ③ 写的 `kb_retrieval` trace（按 `kb_id` 跨该 KB 绑定的 agent），出 **延迟 p50/p95、空召回率（hit_count==0 占比）、score 分布、query/hit 计数**；read-only，复用现成 `agent_observability.aggregate` 的 `query_trace_events(event_type=...)` 模式。**不出真 recall**（那归 /evaluations）。
- **`/evaluations` 接确定性 eval runner**：把 `tests/evaluation/knowledge_base_retrieval_eval.py` 的确定性评估逻辑**提取到 src**（fixture 作数据输入），端点调它在标注 fixture 上算 **recall@k / MRR / hit-ranking**；read-only、确定性 embedding、不碰 index、不调真 LLM（沿用现 spec 约束）。替掉 `wired:False`。
- **修正 observation 的"recall"误导**：把"per-kb recall hit counts"语义改为"proxy 指标"，真 recall 明确归 /evaluations。

### 不在本切片（deferred）
- **citation rate**：全代码无 citation 数据（reply 是否引用了检索 chunk 从未被记）；算它需新 instrumentation（链 retrieval 结果↔reply），超 ③ trace 范围 → **defer**（observation 先不出 citation）。
- retention 调参（复用既有 trace retention）。
- 前端 observation/evaluation 视图增强（本切片只做端点数据；UI 若需另议）。

## Capabilities

### Modified Capabilities
- `kb-admin-api`: "Per-KB observation aggregation" 从"recall hit counts"占位 → **聚合 ③ 的 `kb_retrieval` trace 出 proxy 指标（延迟 p50/p95、空召回率、score 分布、计数）**，read-only；明确**线上不出真 recall**（真 recall 归 /evaluations）；citation defer。
- `kb-eval-entry`: "Retrieval evaluation entry" 从占位 → 端点**真正调确定性 eval runner**（逻辑驻 src、fixture 作数据），返回 **recall@k / MRR / hit-ranking**；保持 read-only / 确定性 embedding / 不碰 index 的既有约束。

## Impact

- **owning packages**：`platform/knowledge_base_management`（`kb_admin_api` 的 observation/evaluation 端点接真实实现）；`knowledge_base`（确定性 eval runner 从 tests 提取到 src，fixture 作数据）；`observability`/复用（按 `kb_retrieval` event_type + kb_id 聚合）
- **public API surface**：`GET /{kb_id}/observation`、`POST /evaluations` 返回真实指标（形状从占位变实数据，向后兼容字段调整）
- **owned tables**：无（读 ③ 的既有 traces；eval 跑 fixture）
- **config namespace**：无（或 eval fixture 路径常量）
- **cross-module dependencies**：platform 读 agent 侧 `kb_retrieval` trace（经现成 `query_trace_events` / agent-observability-view 路径，"平台读 agent 产物"）；eval runner 在 knowledge_base（src），不 import tests；不碰 agent 运行时写路径
- **migration / shim**：无 schema/迁移
- 与 ③ 的关系：③ 是数据源（trace），④ 是读取/聚合 + 离线评估；解耦一致（③ agent 侧写、④ platform 读）
