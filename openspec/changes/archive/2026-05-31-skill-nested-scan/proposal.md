## Why

`skill_registry.scan()`（行 20）当前用 `base.glob("*/SKILL.md")` 收集 Skill——这个 glob 模式**只匹配 skills 目录下恰好一层子目录**中的 `SKILL.md`。任何放在更深层级（如 `skills/crm/contracts/SKILL.md` 或 `skills/team-a/billing/SKILL.md`）的 Skill 都不会被发现，且没有任何提示。

随着 Skill 数量增长，按业务域/团队分组归档是自然诉求，单层平铺难以维护。docs/capabilities/skill.md 现状已标注「仅扫描一级目录，不支持深层嵌套」，并在 v1.0 规划中列出「深层嵌套目录支持：递归扫描 skills/ 下任意层级的 SKILL.md 文件」。

## What Changes

- 将 `scan()` 的扫描从「仅一级子目录」改为**递归扫描 `skills/` 下任意层级**的 `SKILL.md` 文件。
- 保持现有解析与索引逻辑不变：每个发现的 `SKILL.md` 仍按既有方式提取 `name`（缺失回落其所在目录名）与 `description` 建索引。
- 保持现有兜底：`skills/` 目录不存在时仍直接返回，不抛异常。

## Capabilities

### New Capabilities
- `skill-nested-scan`: 递归扫描 `skills/` 目录下任意层级的 `SKILL.md` 文件并纳入索引，不再局限于一级子目录。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。仅扩大扫描覆盖范围，单层 Skill 的发现/解析/匹配行为保持兼容。 -->

## Impact

- **代码**：修改 `src/fleetent/skill_registry.py` 的 `scan()`：将 `base.glob("*/SKILL.md")` 改为递归遍历（`base.rglob("SKILL.md")`），其余索引构建逻辑不变。
- **依赖**：无新增依赖（标准库 `pathlib`）。
- **测试**：扩展 `tests/test_skill_registry.py`：深层嵌套目录中的 `SKILL.md` 被发现并索引；多层级混合（一级 + 多级）全部纳入；`skills/` 不存在时仍安全返回；skills 目录隔离到 `tmp_path`。
- **不影响**：frontmatter 解析（另由 skill-yaml-frontmatter change 处理）、同名冲突处理（另由 skill-name-conflict change 处理）、`FLEETENT_SKILLS_DIR` 解析（另由 skill-env-var change 处理）、关键词匹配与注入。
