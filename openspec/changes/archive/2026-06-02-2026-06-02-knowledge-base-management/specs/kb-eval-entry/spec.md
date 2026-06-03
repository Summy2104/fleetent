## ADDED Requirements

### Requirement: Retrieval evaluation entry
The system SHALL provide a UI entry `/admin/kb/evaluations` to manually trigger the engine's deterministic retrieval evaluation and display the batch's hit / ranking metrics. The evaluation SHALL be read-only analysis: it SHALL NOT modify the index or documents, and SHALL NOT call a real embedding or LLM service. Both admin and viewer SHALL be able to view results.

#### Scenario: Trigger evaluation and show metrics
- **WHEN** an admin triggers a retrieval evaluation run
- **THEN** the system invokes the engine's deterministic evaluation runner and displays the batch's hit and ranking metrics

#### Scenario: Evaluation does not modify the index
- **WHEN** an evaluation run completes
- **THEN** KB documents, chunks, and vector index entries are unchanged

#### Scenario: Evaluation uses deterministic embedding by default
- **WHEN** an evaluation is triggered without explicitly enabling real embedding
- **THEN** the run uses deterministic embedding and isolated storage, never a real embedding service

#### Scenario: Viewer can view evaluation results
- **WHEN** a viewer opens the evaluation entry
- **THEN** the viewer can view the hit / ranking metrics of a run
