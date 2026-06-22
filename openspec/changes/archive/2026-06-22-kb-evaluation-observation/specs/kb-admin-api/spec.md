## MODIFIED Requirements

### Requirement: Per-KB observation aggregation
KB detail 视图 SHALL 呈现按 kb 聚合的**检索 proxy 指标**，数据源为 observability 域的 `kb_retrieval` trace（③ kb-retrieval-audit 所写）；本平面只按 kb 聚合、read-only、不改 index。指标 SHALL 包含：**延迟 p50/p95、空召回率（命中 0 条的占比）、score 分布、query/hit 计数**，可下钻到引用的 session traces。

**线上 SHALL NOT 声称给出真实 recall**：真实 recall@k/MRR 需 ground-truth 标注，只能在离线评估（`/evaluations`）算；observation 平面只给无需标注的 proxy 指标（原占位字段 `recall_hits` 的"recall"语义被纠正为 proxy）。citation 率因当前无 citation 数据而暂不在本平面提供。

#### Scenario: Per-KB proxy 指标只读聚合
- **WHEN** admin 打开某 KB 的 observation 视图
- **THEN** 展示从 `kb_retrieval` trace 聚合的延迟 p50/p95、空召回率、score 分布、计数（不修改 index），可下钻引用 session

#### Scenario: 空召回也被计入
- **WHEN** 该 KB 有命中 0 条的检索
- **THEN** 空召回率指标反映这些 0 命中（来自 ③ 留痕的空召回事件）

#### Scenario: 不在线上谎报真 recall
- **WHEN** observation 视图展示指标
- **THEN** 不出现需 ground-truth 的真实 recall@k/MRR（那归 /evaluations）；只展示 proxy 指标
