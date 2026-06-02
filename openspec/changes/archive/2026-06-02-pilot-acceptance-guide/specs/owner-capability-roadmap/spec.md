## ADDED Requirements

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
