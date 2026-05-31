## Why

`skill_registry._parse_frontmatter()`（行 52-64）当前用「按行查找冒号」的简易扫描解析 SKILL.md 的 frontmatter，仅取出 `name` 与 `description` 两个标量字段，且把每个值都当字符串。这有两个硬伤：

- **无法解析真正的 YAML**：列表（如 `tags: [crm, sales]` 或多行 `- item`）、嵌套结构、引号转义、布尔/数字类型都会被当成裸字符串截断，复杂 frontmatter 直接出错。
- **解析失败静默吞掉**：`_parse_frontmatter` 永远返回一个 dict（哪怕只有空 dict），缺 `---` 分隔符或格式损坏时 `scan()` 会拿到空元数据并悄悄用目录名兜底，运维侧完全无感知——一个写坏的 Skill 会安静地不生效。

v1.0 需要 frontmatter 承载更多治理元数据（`tags` / `platforms` / `version` / `enabled_by_default`），简易扫描无法支撑，且静默失败违背「Skill 没生效要可排查」的诉求。

## What Changes

- 用标准 YAML 解析器（`pyyaml`，已是项目依赖）完整解析 SKILL.md frontmatter，正确支持标量、列表、布尔、数字与嵌套结构。
- 在索引中保留完整解析后的元数据字段，至少识别并承载扩展字段：`tags`（列表）、`platforms`（列表）、`version`（字符串）、`enabled_by_default`（布尔，缺省 `true`）。
- frontmatter 解析失败（YAML 语法错误、顶层不是映射、缺失 `---` 边界）时**明确报警**（结构化 warning 日志，含 SKILL.md 路径与失败原因），并跳过该 Skill，不再静默纳入空元数据。
- `name` / `description` 缺失时同样走报警路径（`name` 缺失回落目录名并 warning；`description` 缺失 warning 但不阻断），保持现有 `match` / `load` 行为兼容。

## Capabilities

### New Capabilities
- `skill-yaml-frontmatter`: 用标准 YAML 解析器完整解析 SKILL.md frontmatter，支持 `tags` / `platforms` / `version` / `enabled_by_default` 等扩展字段；解析失败明确报警并跳过，不静默纳入空元数据。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。匹配/注入既有行为不变；本次仅替换 frontmatter 解析实现并扩展承载字段。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/skill_registry.py`：`_parse_frontmatter()` 改用 `yaml.safe_load` 解析 `---` 之间的内容；新增结构化解析失败处理与 warning 日志；`scan()` 在解析返回 None（失败）时跳过该 Skill。
  - 扩展 `_index` 承载的元数据结构，使其除 `description` / `path` 外还保留 `tags` / `platforms` / `version` / `enabled_by_default`（保持 `match` / `load` / `list_skills` 现有输出兼容）。
- **依赖**：使用既有依赖 `pyyaml`（pyproject 已声明 `pyyaml>=6.0.3` + `types-pyyaml`），不新增依赖。
- **测试**：扩展 `tests/test_skill_registry.py`：列表型 `tags`、布尔 `enabled_by_default`、损坏 YAML 报警并跳过、缺 `---` 边界、扩展字段读取；skills 目录隔离到 `tmp_path`。
- **不影响**：关键词匹配算法、注入流程、`FLEETENT_SKILLS_DIR` 解析（另由 skill-env-var change 处理）、递归扫描（另由 skill-nested-scan change 处理）。
