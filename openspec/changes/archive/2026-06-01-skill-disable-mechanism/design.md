## Context

> 按波次2 skill 轨重规划(2026-05-31)改写:地基为 `skill-read-on-demand`(已归档,清单 + `read_skill`),agent per-agent skill 绑定已废弃(故移除 `agent_blocked` 来源)。

`skill-read-on-demand` 的 `available_skills_prompt` 已经过 `_resolve_disabled_skills` / `_disabled_reason` 排除 `disabled_skills`(配置)与 `enabled_by_default:false`。本 change 在此基础上:加 `enabled` 显式自禁用、把资格判定收敛为单一谓词、把"为何不在清单"的来源写入 trace。

约束(CLAUDE.md):禁止全局可变状态;复用 `eval_logger` trace 出口;mypy strict;行长 100;TDD;测试隔离。

## Goals / Non-Goals

**Goals:**
- frontmatter `enabled: false` 硬关停(优先于 enabled_by_default),排除出清单;`load()` 不受约束。
- 单一资格谓词覆盖全部禁用来源(enabled / disabled_skills / enabled_by_default / audit_blocked)。
- 禁用来源写入 trace,供"为何这个 Skill 不在清单"排查。

**Non-Goals:**
- 不重新实现各来源的判定(disabled_skills 归 builtin-skills、audit_blocked 归 SK5);本 change 统一裁决 + 记录来源。
- 不含 per-agent 黑名单来源(agent skill 绑定已废弃)。
- 不约束 `load()`(显式加载是安全出口)。

## Decisions

### D1:enabled 字段,优先于 enabled_by_default
`SkillEntry` 加 `enabled: bool=True`(SK2 解析填充)。语义:`enabled` 是作者级硬关停,`enabled_by_default` 是默认态——`enabled:false` 一票否决。
**为何**:区分"作者主动停用"与"默认不自动启用";硬关停优先符合直觉。

### D2:单一清单资格谓词
扩展现有 `_disabled_reason(name, entry, disabled)` 为覆盖全部来源的单一判定:返回首个命中的来源标识或 None。`available_skills_prompt` 经它过滤(已如此),`match()` 等若仍存在也经它。
**为何**:多处各写过滤会漂移;单一谓词保证一致,也是来源标识的天然产出点。
**来源优先级(裁决顺序,用于 trace 标识)**:`audit_blocked`(安全最高)> `frontmatter_disabled`(`enabled:false`)> `config_disabled`(`disabled_skills`)> `default_disabled`(`enabled_by_default:false`)。任一命中即排除;trace 记首个(最高优先)命中来源。

### D3:禁用来源写入 trace
某 Skill 被谓词排除时,收集其来源标识,经注入链写入 `eval_logger` 的运行 trace(新增可选字段,默认空、向后兼容)。语义:"本应让模型感知的 Skill 因 X 被挡在清单外"。
**为何**:read-on-demand 下排查问题常是"模型为何没看到/没用某 Skill",来源 trace 直接回答。
**注**:`audit_blocked` 的判定在 SK5;本 change 读取该标志作为一个来源记录。

## Risks / Trade-offs

- [来源 trace 需注入链在构建清单时收集被排除项 → 轻微开销] → 仅在有禁用项时收集与写字段;无禁用零开销、不写字段。
- [`enabled` 与 `disabled_skills` / `enabled_by_default` 语义重叠] → 三者叠加(任一即禁),优先级明确(D2);`enabled` 是作者级、`disabled_skills` 是运维级、`enabled_by_default` 是默认态,各自场景不同。
- [依赖 SK5 的 `audit_blocked`] → SK5 未落地时该来源恒不命中,谓词其余来源照常工作(向后兼容)。

## Open Questions

- 来源 trace 是合进现有 run trace 的一个可选字段,还是独立审计轨迹:倾向前者(复用 eval_logger),与 SK5 审计日志的关系实现时统一。
- `enabled` 与运维级 `disabled_skills` 同时存在的 UI/文档表述,留实现时在 docs/capabilities/skill.md 明确。
