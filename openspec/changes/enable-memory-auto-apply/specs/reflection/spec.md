## MODIFIED Requirements

### Requirement: No automatic application
reflection foundation SHALL 默认只生成建议、不自动应用建议。唯一例外是显式 opt-in 的低风险 user-memory auto-apply
（见 "Opt-in low-risk memory auto-apply" 需求）；该开关默认关闭。Skill 提案与共享记忆/知识库建议在任何情况下 SHALL NOT 被自动应用。

#### Scenario: Skill opportunity does not write skill files
- **WHEN** report 包含 `skill_opportunity` finding
- **THEN** 系统不创建、更新或删除 `skills/` 文件

#### Scenario: Knowledge-base is not required
- **WHEN** knowledge-base 未实现或未启用
- **THEN** `run_reflection()` 仍可基于 traces 和 memory 返回 report

#### Scenario: Auto-apply is off by default
- **WHEN** agent 未显式启用 `reflection.auto_apply.allow_low_risk`
- **THEN** `run_reflection()` 生成的所有 memory 维护提案保持 `pending`，等待人工审批，不被自动应用

## ADDED Requirements

### Requirement: Opt-in low-risk memory auto-apply
当且仅当 agent 配置 `reflection.auto_apply.allow_low_risk` 为 true 时，scheduler 驱动的 reflection 运行 SHALL
对**符合白名单**的 user-memory 维护提案自动应用、无需 owner 人工审批。白名单严格限定为：`risk == "low"`
且 `action` 属于受允许的非破坏 owner-only 动作集（`mark_stale`）。系统 SHALL NOT 自动应用破坏性动作
（`delete` / `merge` / `rewrite` / `compact`）或写共享记忆/知识库的建议（`suggest_shared_memory_or_kb`）——
这些 SHALL 始终要求相应审批人批准。auto-apply SHALL 逐条独立 best-effort：单条应用失败 SHALL 只记录日志、
将该提案保持为待审批状态，且 SHALL NOT 中断 reflection 运行或影响其它提案。

#### Scenario: Low-risk mark_stale auto-applies when opted in
- **WHEN** `reflection.auto_apply.allow_low_risk` 为 true，且 reflection 生成一个 `risk=low`、`action=mark_stale` 的 user-memory 提案
- **THEN** 该提案被自动应用、状态变为 `applied`，无需人工审批

#### Scenario: Shared-memory suggestion never auto-applies
- **WHEN** `reflection.auto_apply.allow_low_risk` 为 true，且生成一个 `risk=low`、`action=suggest_shared_memory_or_kb` 的提案
- **THEN** 该提案 SHALL NOT 被自动应用，保持待审批，等待相应审批人

#### Scenario: Destructive action never auto-applies
- **WHEN** `reflection.auto_apply.allow_low_risk` 为 true，且生成一个 `action ∈ {delete, merge, rewrite, compact}` 的提案
- **THEN** 该提案 SHALL NOT 被自动应用，要求 owner 审批

#### Scenario: Auto-apply failure is isolated
- **WHEN** auto-apply 某条提案时底层应用抛错
- **THEN** 该提案保持待审批并记录日志，reflection 运行继续处理其余提案、不抛出
