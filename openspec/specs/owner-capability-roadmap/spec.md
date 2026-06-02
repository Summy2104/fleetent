# owner-capability-roadmap Specification

## Purpose
Define the cross-capability roadmap used to manage capability modules owned by or strongly
dependent on 常乐, including status, MVP gaps, implementation batches, dependencies, and
MVP-ready criteria.
## Requirements
### Requirement: Owner capability roadmap
The project SHALL maintain a roadmap document for capability modules owned by or strongly
dependent on 常乐.

#### Scenario: Roadmap lists covered capabilities
- **WHEN** a maintainer opens `docs/capabilities/owner-capability-roadmap.md`
- **THEN** it lists observability、memory、long-term context、reflection、vector store、knowledge base、
  evaluation-related work and deployment/config dependencies

#### Scenario: Roadmap defines capability status
- **WHEN** a maintainer reviews the roadmap
- **THEN** each covered capability has a fixed status from 已实现、基础完成、部分完成、仅设计 or 未开始

#### Scenario: Roadmap identifies MVP gaps
- **WHEN** a maintainer reviews a covered capability
- **THEN** the roadmap identifies MVP 必补缺口 and 非 MVP 增强 separately

#### Scenario: Roadmap defines implementation batches
- **WHEN** a maintainer plans the next OpenSpec change
- **THEN** the roadmap shows recommended implementation batches, dependency order and parallelization guidance

#### Scenario: Roadmap defines MVP-ready criteria
- **WHEN** the team evaluates whether 常乐负责模块 are MVP-ready
- **THEN** the roadmap provides explicit criteria for observability、memory、knowledge base、long-term context、
  reflection、vector store and evaluation readiness

### Requirement: Unit test hardening is tracked after MVP foundation
owner-capability-roadmap SHALL track unit test hardening as a post-foundation quality item rather than a new runtime feature.

#### Scenario: Roadmap records unit hardening scope
- **WHEN** `intelligence-unit-test-hardening` is proposed
- **THEN** roadmap docs describe it as quality hardening for observability、memory、long-term context、reflection、vector-store、knowledge-base and deployment/config boundaries
- **AND** roadmap docs state that it does not change runtime behavior or MVP feature scope

#### Scenario: Roadmap records remaining test strategy
- **WHEN** `intelligence-unit-test-hardening` is archived
- **THEN** roadmap docs record the final scoped unit coverage and keep integration / evaluation tests as authoritative for DB runtime, source-of-truth rebuild, connector sync and effect evaluation

### Requirement: Owner roadmap tracks Pilot acceptance entrypoint
owner-capability-roadmap SHALL identify the Pilot acceptance guide as the entrypoint for validating 常乐负责模块 in a test environment.

#### Scenario: Roadmap links Pilot acceptance guide
- **WHEN** 读者查看 `docs/capabilities/owner-capability-roadmap.md`
- **THEN** roadmap 指向 `docs/deployment/pilot-acceptance-guide.md`
- **AND** 说明该指南用于真实测试环境验收，而不是替代自动化测试

#### Scenario: Roadmap separates acceptance from enhancements
- **WHEN** 读者查看 Pilot 后增强列表
- **THEN** roadmap 明确增强 specs 可以与 Pilot 验收并行推进
- **AND** Pilot 后增强不默认阻塞第一次 Pilot 验收
