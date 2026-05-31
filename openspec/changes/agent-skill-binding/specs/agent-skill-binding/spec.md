## ADDED Requirements

### Requirement: per-agent Skill 白名单

agent 定义 SHALL 支持声明 `allowed_skills`（Skill 名 / fnmatch 模式白名单）与可选 `blocked_skills`（在白名单命中后再排除的 fnmatch 模式）。Skill 注入链 MUST 仅注入命中关键词匹配、且其 Skill 名通过 `allowed_skills` 并未被 `blocked_skills` 排除的 Skill。该判定 MUST 复用与工具访问控制（`allowed_tools` / `check_tool_access`）一致的 fnmatch 语义。

#### Scenario: 白名单命中才注入
- **WHEN** 关键词匹配命中某 Skill，且其 Skill 名匹配当前 agent 的 `allowed_skills` 模式、未被 `blocked_skills` 排除
- **THEN** 该 Skill 被加载并注入 system prompt

#### Scenario: 黑名单在白名单内再排除
- **WHEN** 命中的 Skill 名匹配 `allowed_skills`，但同时匹配 `blocked_skills` 中的排除模式
- **THEN** 该 Skill 不被加载、不被注入，即便它通过了白名单

### Requirement: 默认 opt-in 显式绑定

当 agent 未声明 `allowed_skills`（白名单为 `None`）时，Skill 注入链 MUST 不注入任何 Skill。这是相对现状（全局注入命中的 Skill）的行为变更：只有显式声明 `allowed_skills` 的 agent 才会注入匹配到的 Skill。

#### Scenario: 未声明白名单不注入任何 Skill
- **WHEN** 当前 agent 未声明 `allowed_skills`（白名单为 `None`），且用户输入本可关键词命中某 Skill
- **THEN** 注入链不加载、不注入任何 Skill，system prompt 不含 Skill 内容

#### Scenario: 显式声明白名单后注入路径透传生效
- **WHEN** 调用 `run()` / `run_stream()` 时透传了非 `None` 的 `allowed_skills`，且命中的 Skill 名通过该白名单
- **THEN** 该 Skill 经注入链被加载并注入，行为与工具的 `allowed_tools` 透传一致
