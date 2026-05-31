## Why

`skill_registry.scan()`（行 24）以 `_index[name] = (description, str(skill_md))` 写入索引。当两个 `SKILL.md` 解析出相同的 `name`（无论是 frontmatter 显式同名，还是缺失 name 时回落到同名目录），后扫描的会**静默覆盖**先前的——没有任何报警，且谁覆盖谁取决于 glob/遍历顺序，不确定。

这意味着：一个新增/误放的同名 Skill 会悄悄顶掉另一个，运维侧无从察觉「为什么这个 Skill 行为变了/失效了」。随着递归扫描（skill-nested-scan）扩大发现范围，深目录下同名碰撞的概率进一步上升。docs/capabilities/skill.md v1.0 规划明确要求「同名冲突警告：扫描时发现同名 Skill，明确报警并选定一个，不静默覆盖」。

## What Changes

- 扫描过程中检测同名 Skill 冲突：当某 `name` 已在本次扫描中被占用、又出现第二个同名 Skill 时，**明确报警**（结构化 warning，含 name 与两个冲突文件的路径）。
- 按**确定性规则**选定一个胜出者纳入索引，不再依赖遍历顺序的静默覆盖。规则：按 `SKILL.md` 文件路径字符串排序，取排序靠前者为胜出（确定、可预测、与平台无关）。
- 索引最终对每个 name 仍只保留一个条目（保持 `match` / `load` / `list_skills` 现有契约不变）。

## Capabilities

### New Capabilities
- `skill-name-conflict`: 扫描时检测同名 Skill 冲突，明确报警并按确定性规则选定唯一胜出者纳入索引，不再静默覆盖。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。无冲突时索引结果不变；仅冲突场景由「静默覆盖」改为「报警 + 确定性选定」。 -->

## Impact

- **代码**：修改 `src/fleetent/skill_registry.py` 的 `scan()`：写入 `_index` 前检测 name 是否已存在；冲突时记结构化 warning 并按确定性规则（路径排序）决定保留哪个条目。
- **依赖**：无新增依赖。
- **测试**：扩展 `tests/test_skill_registry.py`：两个同名 Skill 触发 warning（捕获 structlog/caplog）；确定性选定（路径排序靠前者胜出，与扫描顺序无关）；无冲突时不报警、索引不变；skills 目录隔离到 `tmp_path`。
- **不影响**：frontmatter 解析（skill-yaml-frontmatter）、递归扫描（skill-nested-scan）、`FLEETENT_SKILLS_DIR`（skill-env-var）、关键词匹配与注入。
