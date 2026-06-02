## ADDED Requirements

### Requirement: Intelligence capability roadmap
The project SHALL maintain a roadmap document for 常乐负责或强依赖的 intelligence-related modules.

#### Scenario: Roadmap lists covered capabilities
- **WHEN** a maintainer opens `docs/capabilities/intelligence-roadmap.md`
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
