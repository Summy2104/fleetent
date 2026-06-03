# skill-disable-mechanism Specification

## Purpose
TBD - created by archiving change skill-disable-mechanism. Update Purpose after archive.
## Requirements
### Requirement: frontmatter enabled 显式禁用单个 Skill

skill_registry SHALL 支持 Skill 经 frontmatter `enabled` 字段(布尔,缺省为真)显式禁用自身。`enabled` 为假的 Skill MUST 被排除出 `available_skills_prompt` 产出的可用 Skill 清单、不向模型展示。该硬关停 MUST 优先于 `enabled_by_default` 默认态:即便 `enabled_by_default` 为真,只要 `enabled` 为假,该 Skill 仍被禁用。`load()` 按名显式加载 MUST NOT 受 `enabled` 约束。

#### Scenario: enabled 为假的 Skill 不进清单
- **WHEN** 某 Skill 的 frontmatter 声明 `enabled: false`
- **THEN** 该 Skill 不出现在 `available_skills_prompt` 清单中,模型感知不到它

#### Scenario: enabled 硬关停优先于默认启用态
- **WHEN** 某 Skill 同时声明 `enabled_by_default: true` 与 `enabled: false`
- **THEN** 该 Skill 仍被禁用、不进清单

#### Scenario: 未声明 enabled 默认启用
- **WHEN** 某 Skill 未声明 `enabled`
- **THEN** 该 Skill 默认启用,正常进入清单,行为与现状一致

#### Scenario: 被禁用 Skill 仍可显式加载
- **WHEN** 某 Skill 经 `enabled: false` 禁用,调用方按名调用 `load()`
- **THEN** 仍返回该 Skill 完整内容,禁用不影响显式加载

### Requirement: 单一清单资格谓词统一裁决禁用

某 Skill「是否进入 `available_skills_prompt` 清单」SHALL 由单一资格谓词裁决,该谓词 MUST 覆盖全部禁用来源:`enabled` 为真 ∧ 不在 `disabled_skills` 配置 ∧ 非 `enabled_by_default:false` ∧ 非 `audit_blocked`(安全审计 severe 拒绝,SK5 判定)。任一来源命中即排除。清单产出 MUST 经该单一谓词,MUST NOT 在多处各自实现独立的启用过滤,以保证结论一致。

#### Scenario: 任一来源命中即排除
- **WHEN** 某 Skill 命中任一禁用来源(frontmatter `enabled:false` / `disabled_skills` / `enabled_by_default:false` / `audit_blocked`)
- **THEN** 该 Skill 不进入清单

#### Scenario: 全部来源均不命中才进清单
- **WHEN** 某 Skill `enabled` 为真、不在 `disabled_skills`、`enabled_by_default` 为真、未被审计拒绝
- **THEN** 该 Skill 进入清单

### Requirement: 禁用来源写入运行日志

当某 Skill 因任一禁用来源被排除出清单时,skill_registry / 注入链 SHALL 将该 Skill 及其禁用来源标识写入该次运行的运行日志(trace),便于事后查询「为什么这个 Skill 没生效」。来源标识取值集合 SHALL 涵盖:`frontmatter_disabled`(`enabled:false`)、`config_disabled`(`disabled_skills`)、`default_disabled`(`enabled_by_default:false`)、`audit_blocked`(SK5 安全审计 severe 拒绝)。`audit_blocked` 由 SK5 判定,本机制仅识别并记录来源。未发生任何 Skill 禁用的正常运行 MUST NOT 写入该字段。

#### Scenario: frontmatter 自禁用写入来源
- **WHEN** 某 `enabled: false` 的 Skill 被排除出清单
- **THEN** 该次运行 trace 含该 Skill 名与来源标识 `frontmatter_disabled`

#### Scenario: 各来源记录对应标识
- **WHEN** 某 Skill 因 `disabled_skills` / `enabled_by_default:false` / `audit_blocked` 被排除
- **THEN** trace 以对应来源标识(`config_disabled` / `default_disabled` / `audit_blocked`)记录该 Skill,本机制仅识别并记录、不重新实现这些来源的判定

#### Scenario: 无禁用的运行不记录该字段
- **WHEN** 一次运行中没有任何 Skill 被禁用排除
- **THEN** trace 不包含禁用来源字段(向后兼容)

