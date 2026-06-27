# agent-stats-aggregation Specification

## MODIFIED Requirements

### Requirement: Model, skill and binding distribution

The system SHALL aggregate per agent: call / token / cost distribution by model and task_type, and binding facts (bound user / channel count, default-agent flag). Skill-hit, memory-hit, and sub_agent-success metrics SHALL follow the dependent-field placeholder rule until emitted.

#### Scenario: Distribution by model and binding facts shown
- **WHEN** an admin opens the model / binding group for an agent
- **THEN** the panel shows call / token distribution by model and task_type, plus bound user / channel counts, and default flag
