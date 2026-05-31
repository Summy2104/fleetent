## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 SK2（`skill-yaml-frontmatter`）已合入：`_index` 条目为结构化元数据且含 `enabled_by_default`（缺省 `True`）；确认条目结构（dict / dataclass）与字段名，本 change 据此新增 `builtin` 字段
- [ ] 1.2 核实 `scan()` 现状的 `*/SKILL.md` 遍历与解析路径，确认内置目录可复用同一遍历/解析逻辑（仅来源目录与 `builtin` 标记不同）
- [ ] 1.3 核实 `match()` 现状遍历索引、首次命中即返回；确认禁用过滤插入点（遍历时跳过被禁用条目）；核实 `Settings` 现状字段以确认 `disabled_skills: list[str]` 的 pydantic-settings 写法

## 2. 内置 Skill 目录与扫描（builtin 标记）

- [ ] 2.1 Write failing tests：`BUILTIN_SKILLS_DIR` 为可 `monkeypatch` 的模块级常量；`scan()` 在 monkeypatch 内置目录（tmp_path）与用户目录（tmp_path）后，内置目录中的 SKILL.md 被索引且条目 `builtin=True`，用户目录中的条目 `builtin=False`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：新增模块级常量 `BUILTIN_SKILLS_DIR = Path(__file__).parent / "builtin_skills"`；`scan()` 先扫内置目录（`builtin=True`）再扫用户目录（`builtin=False`），索引条目新增 `builtin` 字段；新增 `src/fleetent/builtin_skills/` 目录并放入至少一个示例内置 `SKILL.md`。看到绿

## 3. 同名冲突交 SK8（本 change 不实现覆盖）

- [ ] 3.1 确认（无代码）：内置/用户同名冲突的确定性选定与告警由并行 change `skill-name-conflict-warning`(SK8) 负责；本 change 的 `scan()` 仅扫两目录 + 打 `builtin` 标记，**不引入任何同名覆盖/来源优先逻辑**。替换内置 Skill 经禁用开关（第 5 组 `disabled_skills`）实现，不靠隐式同名 shadow
- [ ] 3.2 加回归守卫测试：builtin-skills 自身代码不含「按来源优先选择同名胜出者」分支（scan 两目录同名时不在本 change 做覆盖决策）；避免与 SK8 的路径排序策略重复/打架

## 4. 配置接入：disabled_skills（Settings + 注入点）

- [ ] 4.1 Write failing tests：`Settings` 含 `disabled_skills`（默认空列表）；`skill_registry` 禁用名单注入点（`scan()`/`match()` 可选 `disabled_skills` 参数，缺省惰性读 Settings，参数 > config）按预期解析。看到红
- [ ] 4.2 Implement：`config.py` 的 `Settings` 增加 `disabled_skills: list[str] = []`（env 可配）；`skill_registry` 增加禁用名单注入点（参数 + 惰性 `from fleetent.config import Settings`，同 `context_mgr._default_config()` 模式）。看到绿

## 5. enabled_by_default 接线匹配过滤

- [ ] 5.1 Write failing tests for `match()`：`enabled_by_default=false` 的 Skill 即便关键词命中也不被 `match` 返回、不注入；未声明 `enabled_by_default` 的 Skill 默认启用、可被命中（行为与现状一致）。看到红
- [ ] 5.2 Implement：`match()` 遍历索引时跳过 `enabled_by_default` 为假的条目。看到绿

## 6. 配置强制禁用 + 禁用可观察 + load 不受约束

- [ ] 6.1 Write failing tests：名出现在 `disabled_skills` 的默认启用 Skill 被 `match` 排除、不注入，且记录说明禁用来源的 structlog 日志；被禁用 Skill（默认禁用或配置禁用）经 `load(name)` 仍返回完整内容（启用判定不约束 load）。看到红
- [ ] 6.2 Implement：`match()` 跳过被 `disabled_skills` 命中的条目并记录禁用来源日志（`enabled_by_default=false` vs 配置命中）；`load()` 保持不受启用判定约束。看到绿

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`，项目要求），确认无回归
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 未新增错误模式
- [ ] 7.3 加回归守卫：默认配置（`disabled_skills` 为空、Skill 均未声明 `enabled_by_default` 或声明为真）下，所有 Skill 均参与匹配，行为与本 change 前一致——确认禁用机制默认不改变既有行为
