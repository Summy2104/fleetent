## Context

- 占位端点（`kb_admin_api.py`）：`kb_observation` 返回 `{recall_hits:0, zero_recall_docs:[], sessions:[]}`；`kb_evaluation` 返回 `{metrics:{}, wired:False}`（注释 "Bridges the eval runner"）。`POST /evaluations`(run_evaluation) + `GET /{kb_id}/observation` 已挂、调占位。
- ③ kb-retrieval-audit 已写 `kb_retrieval` trace（payload: result_ids/scores/hit_count/latency_ms/mode/kb_ids/query_hash）。
- 平台读 agent trace 现成模式：`agent_management_console/agent_observability.py::aggregate(agent_name, window)` 用 `query_trace_events(TraceQuery(agent_name=..., event_type=...))` 按 event_type 聚合（D5 stats 页验证过）。
- 确定性 eval harness 现成（**在 tests**）：`tests/evaluation/knowledge_base_retrieval_eval.py`（`validate_fixture`、fixture 含 documents/queries/expected_chunks/forbidden_chunks、`RetrievalEvaluationResult`），fixture 在 `tests/evaluation/fixtures/knowledge_base_retrieval`。

## Goals / Non-Goals

**Goals:**
- `/observation` 出真实 proxy 指标（延迟 p50/p95、空召回率、score 分布、计数），聚合 ③ 的 `kb_retrieval` trace by kb_id；read-only；**不出真 recall**。
- `/evaluations` 真跑确定性 runner（逻辑驻 src），出 recall@k/MRR；保 read-only/确定性 embedding/不碰 index。

**Non-Goals:**
- citation 率（无数据，defer）；retention 调参；前端视图增强（只做端点数据）。

## Decisions

- **D1 · /observation = kb_retrieval 的 proxy 聚合**。新增 kb 聚合器（仿 `agent_observability.aggregate`）：`query_trace_events(event_type="kb_retrieval", ...)` → 按 payload 的 `kb_id` 过滤/聚合（该 KB 可能绑多个 agent → 跨其绑定 agent 聚合）→ 算 latency p50/p95、zero_recall_rate(hit_count==0 占比)、score 分布、query/hit 计数。**复用现成 trace-read 路径**（与 agent stats 同源）；其 managed 多机读取能力如何，kb observation 一并继承（不在本切片修通用 trace-read）。
- **D2 · /evaluations 真接 runner**。把 `tests/evaluation/knowledge_base_retrieval_eval.py` 的**确定性评估逻辑提取到 src**（如 `knowledge_base/retrieval/evaluation.py`），fixture 作**数据输入**（保留 fixture 文件，runner 读它；src 不 import tests）。端点调 runner 在 fixture 上算 recall@k/MRR/hit-ranking。沿用确定性 embedding + 隔离存储 + 不碰真实 index/LLM。
- **D3 · 字段纠正**：`/observation` 的占位 `recall_hits` 改为 proxy 指标字段（如 `latency_ms`, `zero_recall_rate`, `score_distribution`, `query_count`）；移除"线上真 recall"语义。`/evaluations` 才返回 recall@k/MRR。
- **D4 · citation defer**：observation 不含 citation（无数据），proposal/spec 已标。

## Risks / Trade-offs

- **eval runner test→src 提取**：src 不得 import tests。要把评估**逻辑**搬进 src（fixture 仍作数据），且原 `tests/evaluation` 测试改为调 src runner（保其断言），避免重复实现。
- **/observation 跨 agent 聚合 + 继承 trace-read 路径的限制**：一个 KB 绑多 agent，要跨其 agent 聚合 `kb_retrieval`；且复用的 trace-read 路径在 managed 多机下的能力（平台能否读到各 node 上 per-agent trace）本切片不改——kb observation 继承 agent-observability-view 现状，若该路径有限制需在通用层另解。
- **返回形状变更**：占位 → 真实字段，前端 observation/eval 消费方可能要跟字段（本切片只改端点；UI 跟进若需另议，注明避免"以为 UI 也改了"）。
- **proxy ≠ recall 的纪律**：observation 绝不报真 recall（字段命名/文案都不得用会让人以为是真 recall 的名）——这是 #4 的核心判断，测试断言字段不含误导性 recall。
