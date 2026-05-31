# builtin-skills Specification

## Purpose
TBD - created by archiving change builtin-skills. Update Purpose after archive.
## Requirements
### Requirement: 平台内置 Skill 扫描与来源标记

skill_registry SHALL 在扫描用户 `skills/` 目录的同时，扫描平台包内已知位置的内置 Skill 目录；索引中的每个条目 MUST 标记其来源（平台内置 vs 用户自加），以区分二者。内置 Skill 目录路径 MUST 为可注入的模块级常量，便于测试隔离。

#### Scenario: 内置 Skill 被扫描并标记为内置
- **WHEN** 平台内置 Skill 目录中存在一个合法的 SKILL.md
- **THEN** 该 Skill 出现在索引中，且其条目被标记为「平台内置」（`builtin` 为真）

#### Scenario: 用户 Skill 被标记为非内置
- **WHEN** 用户 `skills/` 目录中存在一个合法的 SKILL.md
- **THEN** 该 Skill 出现在索引中，且其条目被标记为「用户自加」（`builtin` 为假）

### Requirement: enabled_by_default 控制默认启用态

skill_registry SHALL 依据每个 Skill 的 `enabled_by_default` 字段决定其是否默认参与自动匹配。`enabled_by_default` 为假的 Skill MUST 被排除出 `match` 的结果、不被自动注入；未声明该字段的 Skill MUST 默认启用，行为与现状一致。

#### Scenario: 默认禁用的 Skill 不参与匹配
- **WHEN** 某 Skill 的 frontmatter 声明 `enabled_by_default: false`，且用户输入命中其关键词
- **THEN** `match` 不返回该 Skill，该 Skill 的内容不被注入

#### Scenario: 未声明 enabled_by_default 的 Skill 默认启用
- **WHEN** 某 Skill 未声明 `enabled_by_default`，且用户输入命中其关键词
- **THEN** 该 Skill 默认启用，能够被 `match` 命中并注入，行为与现状一致

### Requirement: 配置强制禁用指定 Skill

管理员 SHALL 能通过部署级配置（`disabled_skills` 名单）强制禁用指定 Skill。被名单命中的 Skill MUST 被排除出 `match` 的结果、不被自动注入，即使其 `enabled_by_default` 为真。某 Skill 因禁用未参与匹配时，skill_registry MUST 记录一条可观察的日志说明禁用来源。`load` 按名显式加载 MUST 不受启用判定约束。

#### Scenario: 配置禁用覆盖默认启用
- **WHEN** 某默认启用的 Skill 的名出现在 `disabled_skills` 配置名单中，且用户输入命中其关键词
- **THEN** `match` 不返回该 Skill，该 Skill 不被注入，并记录一条说明该 Skill 因配置被禁用的日志

#### Scenario: 被禁用 Skill 仍可显式加载
- **WHEN** 某 Skill 被禁用（默认禁用或配置禁用），调用方按名调用 `load`
- **THEN** 仍返回该 Skill 的完整内容，启用判定不影响显式加载

