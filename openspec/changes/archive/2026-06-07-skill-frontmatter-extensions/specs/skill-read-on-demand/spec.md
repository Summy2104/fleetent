## ADDED Requirements

### Requirement: disable_model_invocation 隐藏 catalog 但保留 read_skill

当某 Skill 的 frontmatter 声明 `disable_model_invocation: true` 时，该 Skill MUST 从 `<available_skills>` catalog 隐藏（模型不主动发现它），但 `read_skill(name)` MUST 仍能按名加载其全文（供其他 Skill 或 hook 组合调用）。这与安全封禁（`audit_blocked`，read_skill 会拒）正交。

#### Scenario: disable_model_invocation 从 catalog 隐藏
- **WHEN** 某 Skill 声明 `disable_model_invocation: true`，构建 catalog
- **THEN** 该 Skill 的 name/description 不出现在 `<available_skills>` 中

#### Scenario: disable_model_invocation 的 skill 仍可 read_skill
- **WHEN** 对一个 `disable_model_invocation: true` 且未被 audit_blocked 的 Skill 调用 `read_skill`
- **THEN** 返回其 SKILL.md 正文（隐藏仅作用于 catalog 发现，不阻断按名加载）

### Requirement: requires_tools 渲染期按可用工具集过滤 catalog

当向 `available_skills_prompt` 传入当前会话的可用工具名集（`available_tools`）时，任一 Skill 若其 `requires_tools` 含不在该集合中的工具，MUST 从 catalog 隐藏。该过滤在渲染期进行（工具可用性每会话可变），与 scan 期的禁用判定正交。当未传入工具集（`available_tools=None`）时 MUST NOT 过滤（向后兼容）。

#### Scenario: 所需工具缺失时隐藏
- **WHEN** 某 Skill 声明 `requires_tools: [run_code]`，渲染时传入的可用工具集不含 `run_code`
- **THEN** 该 Skill 不出现在 catalog 中

#### Scenario: 所需工具齐备时显示
- **WHEN** 某 Skill 声明 `requires_tools: [run_code]`，渲染时传入的可用工具集含 `run_code`
- **THEN** 该 Skill 正常出现在 catalog 中

#### Scenario: 未传工具集时不过滤
- **WHEN** 渲染 catalog 未传入 `available_tools`（None）
- **THEN** requires_tools 不参与过滤，所有 eligible skill 照常渲染（向后兼容）
