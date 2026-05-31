## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `pyyaml` 可直接 `import yaml`（pyproject 已声明 `pyyaml>=6.0.3` + `types-pyyaml`），无需新增依赖
- [x] 1.2 核实 `_index` 仅在 `skill_registry` 内部被读取，对外读取面只有 `match` / `load` / `list_skills` 三个函数，确认索引结构变更的影响边界
- [x] 1.3 确认项目 structlog 日志用法（参照 config.py），定 warning 字段为 `{path, reason}`

## 2. YAML 解析替换（_parse_frontmatter）

- [x] 2.1 Write failing tests for `_parse_frontmatter` 用 YAML 解析：`tests/test_skill_registry.py` 断言含 `tags: [crm, sales]` 的 frontmatter 解析出列表（现简易扫描会截断为字符串）；含 `enabled_by_default: false` 解析为布尔。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：`_parse_frontmatter` 改用 `yaml.safe_load` 解析首尾 `---` 之间的中段，返回 dict。运行 `uv run pytest -x -q` 看到绿

## 3. 解析失败报警并跳过

- [x] 3.1 Write failing tests：损坏 YAML（非法语法）的 SKILL.md 经 `scan` 后不出现在 `_index`，且产生 warning（捕获 structlog 输出/或 caplog）；缺失闭合 `---` 边界同样跳过并 warning；顶层不是映射同样跳过并 warning。看到红
- [x] 3.2 Implement：`_parse_frontmatter` 在缺边界/`YAMLError`/顶层非映射时返回 `None`；`scan` 收到 `None` 时记结构化 warning（含路径与原因）并 `continue` 跳过。看到绿

## 4. 扩展字段承载与缺省值

- [x] 4.1 Write failing tests：声明 `tags` / `platforms` / `version` / `enabled_by_default` 的 Skill 扫描后索引保留这些值；未声明扩展字段的 Skill 取缺省（空列表/空/真）且仍能被 `match` 命中与 `load`；`tags` 为单标量时归一为单元素列表。看到红
- [x] 4.2 Implement：扩展 `_index` 承载结构（含 description/path/tags/platforms/version/enabled_by_default），在 `scan` 处归一类型与填缺省值；保持 `match`/`load`/`list_skills` 既有输出契约不变。看到绿

## 5. 收尾

- [x] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），确认无回归（既有 5 个 skill_registry 测试仍绿）
- [x] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误（索引结构变更后类型注解完整，types-pyyaml 已就位）
