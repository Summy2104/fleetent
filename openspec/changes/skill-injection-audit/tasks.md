> 按波次2 skill 轨重规划改写:地基为 read-on-demand(`available_skills_prompt` + `read_skill`)。

## 1. 前置核实(无代码改动)

- [x] 1.1 核实 read-on-demand 注入两个面:`skill_registry.available_skills_prompt`(清单,含 name/description)与 `tools.read_skill`(全文,经 `load`);确认 severe 拒绝须同时作用于这两处
- [x] 1.2 核实 `SkillEntry` 结构(SK2)与 `scan()` 入索引点,确定审计标注插入位置;确认 `load()` 不受约束的既有口径

## 2. 审计规则层(纯静态)

- [x] 2.1 Write failing tests for `skill_audit`:`audit(content, description)` 对命中已知注入模式的文本返回带规则标识+严重度的命中列表;干净文本返回空;规则表不可变;description 与正文均被检。看到红
- [x] 2.2 Implement:`src/fleetent/skill_audit.py` —— 模块级不可变 `_RULES`(正则/关键短语 + severity + id)+ `audit(content, description) -> list[Hit]`,纯静态、不调 LLM。看到绿

## 3. 接入扫描 + 标注 audit_blocked

- [x] 3.1 Write failing tests:`scan()` 对正文或 description 命中 severe 的 Skill 置 `SkillEntry.audit_blocked=True`(条目仍在 `_index`);仅 suspicious 不置 blocked。skills 目录隔离 tmp_path。看到红
- [x] 3.2 Implement:`SkillEntry` 加 `audit_blocked: bool=False`;`scan()` 入索引前 `audit(body, description)`,有 severe 命中则标注;审计命中写结构化日志,suspicious 在启动扫描输出控制台告警。看到绿

## 4. 清单排除 + read_skill 拒绝

- [x] 4.1 Write failing tests:`available_skills_prompt` 跳过 `audit_blocked` Skill(name/description 不出现);`read_skill(被blocked名)` 返回明确拒绝文本、不返回正文;`load(被blocked名)` 仍返回原文。看到红
- [x] 4.2 Implement:`available_skills_prompt` 过滤 `audit_blocked`(同 disabled);`read_skill` 在 `load` 前检查 `audit_blocked` 返回拒绝文本;`load` 不变。看到绿

## 5. 收尾

- [x] 5.1 全量 `ANTHROPIC_API_KEY=... uv run pytest` 通过,无回归
- [x] 5.2 ruff format/check + mypy 不新增错误模式
- [x] 5.3 验收对照 spec:静态审计(正文+description)、severe 双面拒绝 + load 仍可取、suspicious 记录告警、审计轨迹可观察
