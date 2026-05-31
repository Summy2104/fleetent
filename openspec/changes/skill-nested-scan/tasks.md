## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `scan()` 现用 `base.glob("*/SKILL.md")`（行 20），仅匹配一级子目录；确认其余建索引逻辑与 name 回落（`skill_md.parent.name`）行为
- [x] 1.2 核实 `_index` 键为 name、值为 `(description, path)`，深层路径不改变该结构

## 2. 递归扫描

- [x] 2.1 Write failing tests for 深层嵌套发现：`tests/test_skill_registry.py` 在 `tmp_path/skills/a/b/SKILL.md` 放置一个 Skill，`scan` 后断言其出现在 `_index`（现 glob 只扫一层，应看到红）。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：`scan()` 将 `base.glob("*/SKILL.md")` 改为 `base.rglob("SKILL.md")`，其余不变。运行 `uv run pytest -x -q` 看到绿

## 3. 混合层级与兼容兜底

- [x] 3.1 Write failing tests：一级 + 多级混合目录下的 Skill 全部纳入索引；目录不存在时 `scan` 安全返回且 `_index` 为空不抛异常；一级目录 Skill 的解析与 name 回落结果与现状一致。看到红（或对已绿的兼容用例先确认其作为回归守卫）
- [x] 3.2 Implement / 确认：补齐使混合层级与兜底用例全绿（递归实现已覆盖混合层级；兜底分支沿用既有 `if not base.is_dir(): return`）。看到绿

## 4. 收尾

- [x] 4.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），确认无回归（既有 5 个 skill_registry 测试仍绿）
- [x] 4.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误
