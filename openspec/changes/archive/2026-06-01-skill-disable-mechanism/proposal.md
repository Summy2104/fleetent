## Why

> 注:本 change 原建立在 SK1(L1/L2)+ SK3(match_all 中间产物)+ agent-skill-binding(per-agent 黑名单)地基上。波次2 skill 轨重规划(2026-05-31)后,skill 注入地基已是 `skill-read-on-demand`(已归档,清单 `available_skills_prompt` + `read_skill`,无关键词匹配),且 agent per-agent skill 绑定已废弃。本文件已**按 read-on-demand 重写**:`agent_blocked` 来源移除,「match 命中但被禁」改为「本应进清单但被禁」。

read-on-demand 下,已启用 Skill 经 `available_skills_prompt` 进入 system prompt 清单让模型感知。`skill-read-on-demand` 已实现按 `disabled_skills`(配置)与 `enabled_by_default: false` 排除。本 change 补齐两块:

- **`enabled` 显式自禁用**:Skill 作者可在 frontmatter 写 `enabled: false` 硬关停自身(优先于 `enabled_by_default`)。
- **「为什么这个 Skill 不在清单」可观测**:某 Skill 本应进清单却被排除时,把禁用来源写入运行日志,便于排查。

## What Changes

- 引入 **frontmatter `enabled` 字段**(布尔,缺省 `true`,经 SK2 通用 YAML 解析承载入 `SkillEntry`):`enabled: false` = 显式禁用,排除出清单,**优先于** `enabled_by_default`(自禁用是硬关停)。
- **单一清单资格谓词**:某 Skill「是否进 `available_skills_prompt` 清单」由单一谓词裁决,覆盖全部禁用来源:`enabled: false` ∧ 不在 `disabled_skills` ∧ 非 `enabled_by_default:false` ∧ 非 `audit_blocked`(SK5 安全审计 severe 拒绝)。统一裁决,杜绝多处各写一套过滤。
- **禁用来源写入 trace**:某 Skill 被排除出清单时,把来源标识(`frontmatter_disabled` / `config_disabled` / `default_disabled` / `audit_blocked`)写入运行日志,供「为什么这个 Skill 没生效/不在清单」事后查询。复用 `eval_logger` trace 出口,新增可选字段(默认空,向后兼容)。
- **不改** builtin-skills 的 `disabled_skills` 配置语义;本 change 的 `enabled` 与来源记录与之**叠加生效**(任一来源命中即禁用)。
- `load()` 按名显式加载**不受** `enabled` 约束(与既有口径一致:禁用只约束清单/自动到达模型,不影响显式加载)。

## Capabilities

### New Capabilities
- `skill-disable-mechanism`: Skill 禁用机制——frontmatter `enabled: false` 显式自禁用(优先于 enabled_by_default);单一清单资格谓词统一裁决全部禁用来源(enabled / disabled_skills / enabled_by_default / audit_blocked);某 Skill 被排除出清单时其禁用来源写入运行日志供事后排查;`load()` 显式加载不受约束。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。read-on-demand 的清单/read_skill 机制不变;本次新增 enabled 字段、统一资格谓词、禁用来源 trace。 -->

## Impact

- **代码**:`skill_registry`:`SkillEntry` 加 `enabled: bool=True`(SK2 解析填充);统一 `_disabled_reason`(已存在,扩展覆盖 `enabled`)为单一清单资格判定,`available_skills_prompt` 经它过滤;某 Skill 被排除时收集来源标识,经注入链写入 `eval_logger` trace(新增可选字段)。
- **测试**:`enabled:false` 排除出清单 + 优先于 enabled_by_default + `load()` 仍可取;未声明默认启用;来源标识(frontmatter/config/default/audit)正确写 trace;无禁用的运行不写该字段。
- **不影响**:`disabled_skills` 配置语义(builtin-skills)、`load()` 契约、`read_skill`(显式按名,清单外的禁用项不在清单故模型一般不会读到);不引入新依赖。
- **依赖/协同**:`skill-read-on-demand`(清单 + `_disabled_reason`)、`skill-injection-audit`(SK5,提供 `audit_blocked` 作为第 4 个禁用来源——判定归 SK5,本 change 仅识别并记录来源)。
