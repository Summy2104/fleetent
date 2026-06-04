# capability-roadmaps Specification

## Purpose
Define the roadmap documents used to manage Pilot readiness, related capability clusters,
implementation batches, dependencies, validation gaps and Go / Conditional Go / No-Go criteria.
## Requirements
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
- **THEN** shared memory validation commands use the current `fleetent-admin memory shared ...` command tree
- **AND** the manual does not instruct operators to run removed `fleetent-admin shared-memory ...` commands

#### Scenario: Intelligence validation manual describes real provider opt-in
- **WHEN** a maintainer opens `docs/deployment/intelligence-roadmap-test-manual.md`
- **THEN** real LLM validation instructions explain the explicit opt-in env and provider credential requirements
- **AND** the instructions do not require committing or printing secrets

### Requirement: Unit test hardening is tracked after MVP foundation
Capability roadmaps SHALL track test hardening as post-foundation quality work rather than as a new runtime feature.

#### Scenario: Roadmap records unit hardening scope
- **WHEN** `intelligence-unit-test-hardening` is proposed
- **THEN** roadmap docs describe it as quality hardening for observability、memory、long-term context、reflection、vector-store、knowledge-base and deployment/config boundaries
- **AND** roadmap docs state that it does not change runtime behavior or MVP feature scope

#### Scenario: Roadmap records remaining test strategy
- **WHEN** `intelligence-unit-test-hardening` is archived
- **THEN** roadmap docs record the final scoped unit coverage and keep integration / evaluation tests as authoritative for DB runtime, source-of-truth rebuild, connector sync and effect evaluation

### Requirement: Owner roadmap tracks Pilot acceptance entrypoint
Pilot readiness roadmap SHALL identify the Pilot acceptance guide as the entrypoint for validating the system in a test environment.

#### Scenario: Roadmap links Pilot acceptance guide
- **WHEN** 读者查看 `docs/capabilities/roadmaps/pilot-readiness-roadmap.md`
- **THEN** roadmap 指向 `docs/deployment/pilot-acceptance-guide.md`
- **AND** 说明该指南用于真实测试环境验收，而不是替代自动化测试

#### Scenario: Roadmap separates acceptance from enhancements
- **WHEN** 读者查看 Pilot 后增强列表
- **THEN** roadmap 明确增强 specs 可以与 Pilot 验收并行推进
- **AND** Pilot 后增强不默认阻塞第一次 Pilot 验收

### Requirement: Roadmaps use capability-cluster scope rather than personal ownership scope
Capability roadmaps SHALL describe capability clusters rather than personal ownership boundaries or source package directories.

#### Scenario: Intelligence roadmap is not confused with intelligence package internals
- **WHEN** 读者查看 `docs/capabilities/roadmaps/intelligence-roadmap.md`
- **THEN** 文档说明其范围是 Memory、Long-term Context、Reflection、Vector Store 和 Knowledge Base capability cluster
- **AND** 不把该 roadmap 描述成 `src/fleetent/intelligence/` package 的代码目录规划

#### Scenario: Roadmaps reflect package migrations
- **WHEN** 读者查看 roadmap 的当前能力地图或后续缺口
- **THEN** 已完成 package migrations 后的 canonical package 名称保持一致
