# kb-eval-entry Specification

## Purpose
TBD - created by archiving change 2026-06-02-knowledge-base-management. Update Purpose after archive.
## Requirements
### Requirement: Retrieval evaluation entry
The system SHALL provide a UI entry `/admin/kb/evaluations` to manually trigger the engine's deterministic retrieval evaluation and display the batch's hit / ranking metrics. The evaluation SHALL be read-only analysis: it SHALL NOT modify the index or documents, and SHALL NOT call a real embedding or LLM service. Both admin and viewer SHALL be able to view results.

端点 SHALL **真正调用确定性评估 runner**（不再返回占位 `wired:false`）：runner 逻辑 SHALL 驻于 `src`（KB 组件内、可被端点 import；标注 fixture 作数据输入），在标注 fixture（含 documents/queries/expected_chunks/forbidden_chunks）上计算并返回 **recall@k、MRR、hit-ranking** 等指标。

#### Scenario: Trigger evaluation and show metrics
- **WHEN** an admin triggers a retrieval evaluation run
- **THEN** the system invokes the engine's deterministic evaluation runner and displays the batch's hit and ranking metrics (recall@k / MRR)

#### Scenario: 端点真实接通 runner（非占位）
- **WHEN** 调 `/evaluations`
- **THEN** 返回在标注 fixture 上算出的真实 recall@k / MRR，而非 `{metrics:{}, wired:false}` 占位

#### Scenario: Evaluation does not modify the index
- **WHEN** an evaluation run completes
- **THEN** KB documents, chunks, and vector index entries are unchanged

#### Scenario: Evaluation uses deterministic embedding by default
- **WHEN** an evaluation is triggered without explicitly enabling real embedding
- **THEN** the run uses deterministic embedding and isolated storage, never a real embedding service

#### Scenario: Viewer can view evaluation results
- **WHEN** a viewer opens the evaluation entry
- **THEN** the viewer can view the hit / ranking metrics of a run

