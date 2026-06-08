## MODIFIED Requirements

### Requirement: Unified message format
The system SHALL define `NormalizedMessage` as the contract between adapters and the agent pipeline.

#### Scenario: NormalizedMessage fields
- **WHEN** any adapter normalizes a message
- **THEN** the resulting object MUST contain: `platform`, `session_id`, `user_id`, `text`, `attachments` (list, may be empty), `reply_func` (async callable)
- **AND** MAY contain `progress_func` (optional async callable, default `None`); when `None` the pipeline behaves identically to the previous version

#### Scenario: Adapter without progress_func preserves existing behavior
- **WHEN** an adapter constructs `NormalizedMessage` without setting `progress_func`
- **THEN** normalizer.route() runs identically to the pre-change version with no side effects
