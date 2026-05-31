> 按波次2 skill 轨重规划改写:地基为 read-on-demand(`available_skills_prompt` + `_disabled_reason`);移除 agent_blocked 来源(agent skill 绑定已废弃)。

## 1. 前置核实(无代码改动)

- [ ] 1.1 核实 `skill_registry` 现状:`available_skills_prompt` 经 `_resolve_disabled_skills` / `_disabled_reason` 已排除 `disabled_skills` 与 `enabled_by_default:false`;确认扩展点(把 `enabled` 与 `audit_blocked` 并入 `_disabled_reason`)
- [ ] 1.2 核实 `SkillEntry`(SK2)与 `eval_logger` trace 出口(新增可选字段的既有模式,如 stop_reason/error_category)

## 2. frontmatter enabled 字段

- [ ] 2.1 Write failing tests:`enabled:false` 的 Skill 不进 `available_skills_prompt` 清单;优先于 `enabled_by_default:true`;未声明默认启用;`load()` 仍返回原文。skills 目录隔离 tmp_path。看到红
- [ ] 2.2 Implement:`SkillEntry` 加 `enabled: bool=True`(scan 经 SK2 解析填充);`_disabled_reason` 纳入 `enabled` 判定。看到绿

## 3. 单一清单资格谓词 + 来源标识

- [ ] 3.1 Write failing tests:`_disabled_reason`(或资格谓词)对各来源返回正确标识——`frontmatter_disabled` / `config_disabled` / `default_disabled` / `audit_blocked`;优先级 audit > frontmatter > config > default;全不命中返回 None。看到红
- [ ] 3.2 Implement:扩展 `_disabled_reason` 为单一资格谓词,按优先级返回首个命中来源标识或 None;`available_skills_prompt` 经它过滤(已如此),纳入 `enabled` 与 `audit_blocked`(读 SK5 的标志,SK5 未落地时恒不命中)。看到绿

## 4. 禁用来源写入 trace

- [ ] 4.1 Write failing tests:构建清单时被排除的 Skill 及其来源标识写入 `eval_logger` 运行 trace(新增可选字段);无禁用的运行不写该字段(向后兼容)。看到红
- [ ] 4.2 Implement:注入链构建清单时收集被排除项(name + 来源),`log_run` 增可选 `disabled_skills_trace` 字段(默认空、非空才写)。看到绿

## 5. 收尾

- [ ] 5.1 全量 `ANTHROPIC_API_KEY=... uv run pytest` 通过,无回归;与 builtin-skills 的 `disabled_skills` 叠加生效用例
- [ ] 5.2 ruff format/check + mypy 不新增错误模式
- [ ] 5.3 验收对照 spec:enabled 硬关停 + 优先 + load 不受限、单一谓词覆盖全部来源、来源写 trace、无禁用不写字段
- [ ] 5.4 docs/capabilities/skill.md 补 `enabled`(作者级)vs `disabled_skills`(运维级)vs `enabled_by_default`(默认态)的区分与优先级
