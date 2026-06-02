## ADDED Requirements

### Requirement: Skill reflection proposal public API
reflection SHALL 提供 Skill proposal lifecycle，用于把 skill opportunity 转成受控待审建议。

#### Scenario: Skill proposal API is importable
- **WHEN** 调用方从 `fleetent.intelligence.reflection` 导入 `SkillProposal`、`generate_skill_proposals`、`approve_skill_proposal`、`reject_skill_proposal` 和 `apply_skill_proposal`
- **THEN** 导入成功

#### Scenario: Skill proposals are persisted
- **WHEN** 数据库 migration 运行到最新版本
- **THEN** 数据库包含 reflection-owned `skill_proposals` 表

### Requirement: Skill proposal types
系统 SHALL 支持 create、update 和 deprecate 三类 Skill proposal。

#### Scenario: Create skill proposal
- **WHEN** traces 或 reflection finding 显示重复任务模式且现有 skill 未覆盖
- **THEN** 系统可以生成 `type="create_skill"` proposal

#### Scenario: Update skill proposal
- **WHEN** 现有 skill 经常触发但失败、缺少约束或步骤过期
- **THEN** 系统可以生成 `type="update_skill"` proposal

#### Scenario: Deprecate skill proposal
- **WHEN** 现有 skill 长期未触发、重复或持续造成低质量结果
- **THEN** 系统可以生成 `type="deprecate_skill"` proposal

#### Scenario: Single ordinary task is ignored
- **WHEN** trace 只包含一次普通任务且没有稳定重复模式
- **THEN** 系统不生成 Skill proposal

### Requirement: Skill proposal evidence and draft
每个 Skill proposal SHALL 包含可审查的 reason、evidence 和建议内容。

#### Scenario: Proposal includes evidence
- **WHEN** proposal 被创建
- **THEN** proposal 包含 reason、evidence_refs、risk_level 和 created_at

#### Scenario: Create proposal includes draft
- **WHEN** proposal type 为 `create_skill`
- **THEN** proposal 包含 suggested_draft 或等价 skeleton

#### Scenario: Update proposal includes diff
- **WHEN** proposal type 为 `update_skill`
- **THEN** proposal 包含 suggested_diff 或 suggested replacement summary

#### Scenario: Persisted proposal is redacted
- **WHEN** proposal 被保存
- **THEN** payload 不包含完整用户 transcript

### Requirement: Skill proposal review lifecycle
Skill proposal SHALL 默认 pending，只有 approved proposal 可以 apply。

#### Scenario: New proposal is pending
- **WHEN** proposal 被创建
- **THEN** status 为 `pending`

#### Scenario: Pending proposal can be approved
- **WHEN** reviewer approve pending proposal
- **THEN** status 变为 `approved`
- **AND** 系统记录 reviewer 和 reviewed_at

#### Scenario: Pending proposal can be rejected
- **WHEN** reviewer reject pending proposal
- **THEN** status 变为 `rejected`
- **AND** 系统记录 reviewer、reviewed_at 和 rejection reason

#### Scenario: Rejected proposal cannot apply
- **WHEN** 调用 apply rejected proposal
- **THEN** 系统 fail fast
- **AND** 不修改 skill

### Requirement: Skill proposal apply boundary
Skill proposal apply SHALL 通过 skill public boundary 执行，不得绕过边界任意写文件。

#### Scenario: Approved proposal can apply
- **WHEN** approved proposal 被 apply
- **THEN** 系统调用 skill public API 或 skill management boundary
- **AND** apply 成功后 status 变为 `applied`

#### Scenario: Apply does not write arbitrary files
- **WHEN** apply proposal
- **THEN** 系统不得根据 LLM 输出直接写任意路径
- **AND** skill name、path 和 content 必须经过 validation

#### Scenario: Missing skill boundary fails fast
- **WHEN** skill public apply boundary 不可用
- **THEN** apply 明确失败或返回 unsupported
- **AND** 不直接修改 `skills/`

### Requirement: Skill proposal generation avoids real LLM by default
系统 SHALL 默认使用 deterministic generator 生成 proposal draft / diff skeleton。

#### Scenario: Real LLM draft generation is skipped by default
- **WHEN** 未设置真实 LLM opt-in 环境变量
- **THEN** 系统不调用真实 LLM 生成 skill draft

#### Scenario: Deterministic generator is testable
- **WHEN** 默认测试运行
- **THEN** proposal draft / diff 输出稳定

### Requirement: Skill proposal evaluation
系统 SHALL 提供 deterministic evaluation，验证 proposal 生成质量和误报控制。

#### Scenario: Expected proposals are validated
- **WHEN** evaluation fixture 包含重复任务、失败 skill 或未使用 skill signal
- **THEN** expected create/update/deprecate proposal 出现

#### Scenario: Forbidden proposals are rejected
- **WHEN** evaluation fixture 只包含普通单次任务
- **THEN** 不生成 forbidden proposal
