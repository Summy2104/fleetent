## ADDED Requirements

### Requirement: Owner roadmap uses owner scope rather than intelligence package scope
owner-capability-roadmap SHALL describe 常乐负责或强依赖的 capability modules，而不是 `src/fleetent/intelligence/` package 的专属路线图。

#### Scenario: Owner roadmap is not confused with intelligence package
- **WHEN** 读者查看 `docs/capabilities/owner-capability-roadmap.md`
- **THEN** 文档说明其范围是常乐负责或强依赖的 capability modules
- **AND** 不把该 roadmap 描述成 `src/fleetent/intelligence/` package 的代码目录规划

#### Scenario: Owner roadmap reflects package migrations
- **WHEN** 读者查看 owner roadmap 的当前能力地图或后续缺口
- **THEN** 已完成 package migrations 后的 canonical package 名称保持一致
