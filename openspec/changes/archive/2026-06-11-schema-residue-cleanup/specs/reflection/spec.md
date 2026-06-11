# reflection Delta

## MODIFIED Requirements

### Requirement: Skill reflection proposal public API
reflection SHALL 提供 Skill proposal lifecycle，用于把 skill opportunity 转成受控待审建议。

#### Scenario: Skill proposal API is importable
- **WHEN** 调用方从 `fleetent.reflection` 导入 `SkillProposal`、`generate_skill_proposals`、`approve_skill_proposal`、`reject_skill_proposal` 和 `apply_skill_proposal`
- **THEN** 导入成功

#### Scenario: Skill proposals are persisted
- **WHEN** per-agent `agent_state.db` 的嵌入式迁移运行到最新版本
- **THEN** Skill proposal 持久化在统一的 `reflection_proposals` 表（`domain='skill'`），不存在独立的 `skill_proposals` 表
- **AND** 管理库中不存在 `skill_proposals` 表
