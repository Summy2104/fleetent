## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `match()` 现状为「首次命中即返回」（skill_registry.py 行 59-70），确认 `_index` 遍历顺序为扫描插入序、需确定性化
- [ ] 1.2 核实 SK2 的 frontmatter 解析路径（`scan` 行 39-56），确认新增 `exclusive` 字段可经 `bool(frontmatter.get("exclusive", False))` 填充 `SkillEntry`
- [ ] 1.3 核实 `agent_loop` 注入链消费 `match`/`load` 的位置（`run_sync()` 行 408-415 / `run_stream()` 行 451-453；`run()` 行 234 不做注入）与两条路径的返回/流式契约，确认 design D4 定的默认承载形态 `(system_prompt, ask_signal | None)` 可在两处呈现（CLI 提示文本 / SSE 事件）

## 2. 全部命中匹配（skill_registry.match_all）

- [ ] 2.1 Write failing tests for `match_all()`：`tests/test_skill_registry.py` 断言两个 description 均被用户输入命中的 Skill 都出现在返回列表中；返回顺序确定（名称升序），不依赖扫描插入序；无命中返回空列表。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `match_all(user_input) -> list[str]`：复用现有命中判据收集全部命中，按名称升序返回。看到绿

## 3. exclusive 字段解析

- [ ] 3.1 Write failing tests：含 `exclusive: true` 的 SKILL.md 扫描后 `SkillEntry.exclusive` 为真；未声明时缺省为假。看到红
- [ ] 3.2 Implement：`SkillEntry` 新增 `exclusive: bool = False`，`scan` 处由 frontmatter 填充。看到绿

## 4. 注入链多命中：L1 共存 + L2 单注入

- [ ] 4.1 Write failing tests：用户输入同时命中两个非互斥 Skill 时，system prompt 含两者的 L1 摘要（名称+描述），但只含其中一个（确定性选定者）的 L2 全文。mock `get_async_client_and_config`，skills 目录隔离 `tmp_path`。看到红
- [ ] 4.2 Implement：注入链改用 `match_all`（替换 SK1 落地的 `match()` 首个命中 L2 选定），L1 共存（复用 SK1 的 `l1_summary()`），L2 取确定性首个非互斥命中注入。看到绿

## 5. 互斥命中产出询问信号

- [ ] 5.1 Write failing tests：命中集合中含 `exclusive: true` 的 Skill 时，注入链不注入任何 L2 全文，并产出含候选 Skill 名的 `ask_signal`（按 design D4 默认形态：注入辅助函数返回 `(system_prompt, AskSignal(candidates=[...]))`，断言 candidates 含两个互斥候选名、system_prompt 不含任一 L2 全文）。看到红
- [ ] 5.2 Implement：注入链判定互斥命中 → 不注入 L2 → 返回结构化 `ask_signal`（候选名列表）；`run_sync`/`run_stream` 各自呈现（CLI 提示 / SSE 事件），不耦合具体交互通道。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
