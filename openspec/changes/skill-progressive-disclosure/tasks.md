## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 SK2 已合入：`_index` 为 `dict[str, SkillEntry]`，`SkillEntry` 含 `description`，可作 L1 摘要数据源（skill_registry.py 行 14-26）
- [ ] 1.2 核实 `agent_loop` 注入链现状：`run_sync()` 行 408-415 与 `run_stream()` 行 451-453 的 `scan→match→load` 拼接形态（`run()` 行 234 只收预构建 messages、不做注入），确认改为「L1 始终 + L2 命中」后增量行为
- [ ] 1.3 确认 `match` / `load` / `list_skills` 对外契约（skill_registry.py 行 59-80），确认新增 `l1_summary()` 不改三者

## 2. L1 摘要产出（skill_registry.l1_summary）

- [ ] 2.1 Write failing tests for `l1_summary()`：`tests/test_skill_registry.py` 断言扫描多个 Skill 后返回的清单文本含每个 Skill 的 `name` 与 `description`；空索引返回空串；skills 目录隔离到 `tmp_path`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `l1_summary() -> str`：遍历 `_index` 渲染「名称+描述」清单，不改 `match`/`load`/`list_skills`。运行 `uv run pytest -x -q` 看到绿

## 3. 注入链分级（agent_loop：L1 始终 + L2 命中）

- [ ] 3.1 Write failing tests：命中某 Skill 时 `run_sync()`（行 408-415）构造的 system prompt 同时包含 L1 清单（该 Skill 名）与该 Skill 的 L2 全文；`run_stream()`（行 451-453）同理。mock `get_async_client_and_config`，skills 目录隔离到 `tmp_path`。看到红
- [ ] 3.2 Implement：注入链先拼 L1 清单（非空时），命中再追加 L2 全文，L1/L2 分段拼接。看到绿
- [ ] 3.3 Write failing tests：未命中任何关键词时 system prompt 仍包含 L1 清单（全量 Skill 名），但不包含任何 Skill 的 L2 全文正文。看到红
- [ ] 3.4 Implement 使未命中路径注入 L1、不注入 L2。看到绿

## 4. L3 边界（附属资源不进 prompt）

- [ ] 4.1 Write failing tests：某 Skill 的 SKILL.md 引用了附属文件（如 `references/x.md`），命中注入 L2 后，system prompt 不包含该附属文件的内容（只含 SKILL.md 正文）。看到红
- [ ] 4.2 Implement / 确认：注入链只读 `load()`（SKILL.md 正文），不读取任何被引用的附属文件。看到绿

## 5. 收尾

- [ ] 5.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归（既有 skill_registry 与 agent_loop 用例仍绿）。**显式核对回归风险**：本 change 改为「始终注入 L1 清单」会让每个请求的 system prompt 在原内容外多出 L1 段，现有 `tests/test_agent_loop.py` 中断言 system prompt 精确内容 / 长度 / 不含额外段的用例可能因此回归——逐个核对并按新基线（含 L1 清单）更新断言，确认变更是预期而非缺陷
- [ ] 5.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 5.3 `uv run mypy src` 无新增错误
