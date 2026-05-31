## 1. 前置核实（实现前的事实确认，无代码改动）

- [x] 1.1 核实 `scan()` 行 15 实际读取的是旧名 `os.environ.get("MINI_AGENT_SKILLS_DIR", "skills")`（确认本 change 是真实重命名，非「仅确认」）
- [x] 1.2 核实 CLAUDE.md「环境变量」节与 docs/capabilities/skill.md 均规定正确名为 `FLEETENT_SKILLS_DIR`，文档与实现不一致
- [x] 1.3 确认解析优先级现状：显式 `skills_dir` 参数 > 环境变量 > 默认 `"skills"`

## 2. 环境变量名更正

- [x] 2.1 Write failing tests：`monkeypatch.setenv("FLEETENT_SKILLS_DIR", <tmp_path/skills>)` 且不显式传参时，`scan()` 使用该目录（现读旧名，应看到红）。运行 `uv run pytest -x -q` 看到红
- [x] 2.2 Implement：将行 15 的 `MINI_AGENT_SKILLS_DIR` 改为 `FLEETENT_SKILLS_DIR`，默认值保持 `"skills"`。运行 `uv run pytest -x -q` 看到绿

## 3. 回落与旧名防回归

- [x] 3.1 Write failing tests：未设置 `FLEETENT_SKILLS_DIR`（`monkeypatch.delenv` 容错）时回落默认 `./skills`；仅设置旧名 `MINI_AGENT_SKILLS_DIR` 时不生效、回落默认（防回归）；显式传参时忽略环境变量。看到红（旧名防回归用例在改名前应失败）
- [x] 3.2 Implement / 确认：使三类用例全绿（更名后旧名自然不再被读取；回落与传参优先级沿用现状逻辑）。看到绿

## 4. 收尾

- [x] 4.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），确认无回归（既有 5 个 skill_registry 测试仍绿）
- [x] 4.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿；`uv run mypy src` 不新增错误
