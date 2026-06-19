## MODIFIED Requirements

### Requirement: Pilot readiness roadmap

The project SHALL maintain a thin Pilot readiness roadmap that links detailed capability-cluster
roadmaps and identifies Pilot validation entrypoints.

#### Scenario: Roadmap lists covered capabilities
- **WHEN** a maintainer opens `docs/capabilities/roadmaps/pilot-readiness-roadmap.md`
- **THEN** it lists major capability clusters, their detail documents, Pilot risk and validation entrypoints

#### Scenario: Roadmap defines capability status
- **WHEN** a maintainer reviews the roadmap
- **THEN** each covered capability has a fixed status from 已实现、基础完成、部分完成、仅设计 or 未开始

#### Scenario: Roadmap identifies MVP gaps
- **WHEN** a maintainer reviews a covered capability
- **THEN** roadmap docs identify MVP 必补缺口 and 非 MVP 增强 separately

#### Scenario: Roadmap defines implementation batches
- **WHEN** a maintainer plans the next OpenSpec change
- **THEN** the relevant capability-cluster roadmap shows recommended implementation batches, dependency order and parallelization guidance

#### Scenario: Roadmap defines MVP-ready criteria
- **WHEN** the team evaluates whether Pilot is ready
- **THEN** roadmap docs provide explicit criteria for readiness, validation evidence and remaining gaps

#### Scenario: Intelligence validation manual uses current CLI entrypoints
- **WHEN** a maintainer opens `docs/deployment/intelligence-roadmap-test-manual.md`
- **THEN** shared memory validation commands use the current `fleetent admin memory shared ...` command tree
- **AND** the manual does not instruct operators to run removed `fleetent admin shared-memory ...` commands

#### Scenario: Intelligence validation manual describes real provider opt-in
- **WHEN** a maintainer opens `docs/deployment/intelligence-roadmap-test-manual.md`
- **THEN** real LLM validation instructions explain the explicit opt-in env and provider credential requirements
- **AND** the instructions do not require committing or printing secrets
