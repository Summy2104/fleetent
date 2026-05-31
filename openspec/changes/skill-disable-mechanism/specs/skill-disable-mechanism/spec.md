## ADDED Requirements

### Requirement: frontmatter enabled 显式禁用单个 Skill

skill_registry SHALL 支持 Skill 经 frontmatter `enabled` 字段（布尔，缺省为真）显式禁用自身。`enabled` 为假的 Skill MUST 被排除出 `match` 的结果、不被自动注入。该硬关停 MUST 优先于 `enabled_by_default` 默认态判定：即便 `enabled_by_default` 为真，只要 `enabled` 为假，该 Skill 仍被禁用。`load` 按名显式加载 MUST NOT 受 `enabled` 约束。

#### Scenario: enabled 为假的 Skill 不参与匹配
- **WHEN** 某 Skill 的 frontmatter 声明 `enabled: false`，且用户输入命中其关键词
- **THEN** `match` 不返回该 Skill，该 Skill 的内容不被注入

#### Scenario: enabled 硬关停优先于默认启用态
- **WHEN** 某 Skill 同时声明 `enabled_by_default: true` 与 `enabled: false`
- **THEN** 该 Skill 仍被禁用、不被注入

#### Scenario: 未声明 enabled 默认启用
- **WHEN** 某 Skill 未声明 `enabled`，且用户输入命中其关键词
- **THEN** 该 Skill 默认启用，能被 `match` 命中并注入，行为与现状一致

#### Scenario: 被禁用 Skill 仍可显式加载
- **WHEN** 某 Skill 经 `enabled: false` 禁用，调用方按名调用 `load`
- **THEN** 仍返回该 Skill 的完整内容，禁用不影响显式加载

### Requirement: 禁用来源写入运行日志

当某 Skill 因任一禁用来源未参与注入、而其本可被关键词命中时，skill_registry / 注入链 SHALL 将该 Skill 及其禁用来源标识写入该次运行的运行日志（trace），便于事后查询「为什么这个 Skill 没有生效」。禁用来源标识取值集合 SHALL 涵盖 frontmatter 自禁用、配置名单禁用、默认态关闭、per-agent 黑名单，以及安全审计 severe 拒绝（`audit_blocked`）——后者由并行的安全审计机制（SK5）判定，本机制仅识别并记录来源，统一纳入同一「为什么这个 Skill 没生效」trace。未发生任何 Skill 禁用的正常运行 MUST NOT 写入该字段。

#### Scenario: frontmatter 自禁用写入禁用来源
- **WHEN** 某 `enabled: false` 的 Skill 本可被用户输入命中，但因禁用未注入
- **THEN** 该次运行的 trace 记录中包含该 Skill 名与禁用来源（标识为 frontmatter 自禁用）

#### Scenario: 无禁用的运行不记录禁用字段
- **WHEN** 一次运行中没有任何 Skill 因禁用被跳过
- **THEN** trace 记录中不包含禁用来源字段

#### Scenario: 多来源禁用记录对应来源
- **WHEN** 某 Skill 因配置名单、默认态关闭、per-agent 黑名单或安全审计 severe 拒绝（`audit_blocked`，均由并行机制判定）而被禁用并跳过
- **THEN** trace 记录中以对应的禁用来源标识记录该 Skill，本机制仅识别并记录来源、不重新实现这些来源的判定

### Requirement: 注入裁决经单一 injectable 谓词

某 Skill 「当前是否可被自动注入」SHALL 由单一谓词 `injectable(skill, request)` 裁决：命中 ∧ `enabled` ∧ 不在 `disabled_skills` ∧ 非默认态关闭 ∧ 过 per-agent 绑定 ∧ 非安全审计 severe 拒绝（`audit_blocked`）。L1（前置/基线注入）与 L2（关键词匹配注入）以及全部注入点 MUST 通过同一谓词裁决，MUST NOT 各自实现独立的启用过滤，以保证不同注入路径对同一 Skill 给出一致的启用结论。

#### Scenario: L1 与 L2 对被禁用 Skill 给出一致结论
- **WHEN** 某 Skill 被任一禁用来源（如 `enabled: false` 或安全审计拒绝）排除
- **THEN** 无论该 Skill 经 L1 还是 L2 路径，均不被注入（L1 不得绕过禁用 / 审计判定）

#### Scenario: 所有注入点共享同一裁决
- **WHEN** 同一 Skill 在不同注入点（如 run_sync / run_stream / IM 路径）被评估
- **THEN** 各注入点对其是否注入的结论一致，因为它们查询的是同一 `injectable` 谓词
