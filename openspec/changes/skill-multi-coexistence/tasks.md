## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `match()` 现状为「先过 disabled 过滤、首次命中即返回」（skill_registry.py **行 94**，`match(user_input, disabled_skills=None)`，经 `_resolve_disabled_skills` + `_disabled_reason`），确认 `_index` 遍历顺序为扫描插入序、需确定性化；确认 **`match_all` 必须保留这套 disabled 过滤**
- [ ] 1.2 核实 SK2 的 frontmatter 解析路径（`scan` 处填充 `SkillEntry`），确认新增 `exclusive` 字段可经 `bool(frontmatter.get("exclusive", False))` 填充
- [ ] 1.3 核实 `agent_loop` 注入链经 `_matched_skill_content(user_input, allowed_skills, blocked_skills)`（**行 231**：`match` → `check_skill_access` agent 绑定门控 → `load`），消费点 `run_sync()`（行 496）/ `run_stream()`（行 531），`run()` 不做注入；核实**第三处注入点** `im_gateway/normalizer.py`（行 91-100，独立 `match` + `check_skill_access` + `load`）。确认 design D4 默认承载形态 `(system_prompt, ask_signal | None)` 可在三处呈现，且 D6 的 `injectable` 谓词逐候选保留 disabled 过滤 + 绑定门控

## 2. 全部命中匹配（skill_registry.match_all，保留 disabled 过滤）

- [ ] 2.1 Write failing tests for `match_all()`：`tests/test_skill_registry.py` 断言两个 description 均被命中的 Skill 都出现在返回列表；返回顺序确定（名称升序），不依赖扫描插入序；无命中返回空列表；**禁用项被过滤**（`enabled_by_default=False` 或名在 `disabled_skills` 入参内的命中 Skill **不出现**在 `match_all` 结果中，与 `match` 一致）。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `match_all(user_input, disabled_skills=None) -> list[str]`：复用现有命中判据 + `_resolve_disabled_skills` / `_disabled_reason` 禁用过滤，收集全部命中且未被禁用的项，按名称升序返回。看到绿

## 3. exclusive 字段解析

- [ ] 3.1 Write failing tests：含 `exclusive: true` 的 SKILL.md 扫描后 `SkillEntry.exclusive` 为真；未声明时缺省为假。看到红
- [ ] 3.2 Implement：`SkillEntry` 新增 `exclusive: bool = False`，`scan` 处由 frontmatter 填充。看到绿

## 4. 注入链多命中：L1 共存 + L2 单注入 + 逐候选保留绑定门控

- [ ] 4.1 Write failing tests：(a) 用户输入同时命中两个非互斥 Skill 时，system prompt 含两者的 L1 摘要（名称+描述），但只含其中一个（确定性选定者）的 L2 全文；(b) **绑定门控不回归**：当某命中 Skill 不在 `allowed_skills` 白名单（或在 `blocked_skills`）时，其 L2 不被注入、且不作为 L2 选定对象（逐候选过 `check_skill_access`）。mock `get_async_client_and_config`，skills 目录隔离 `tmp_path`。看到红
- [ ] 4.2 Implement：注入辅助改用 `match_all`（替换 SK1 落地的 `match()` 首个命中 L2 选定），逐候选应用 `check_skill_access`（D6 `injectable` 谓词），L1 共存（复用 SK1 的 `l1_summary()`），L2 取确定性首个 `injectable` 非互斥命中注入；三处注入点（`run_sync`/`run_stream` 经 `_matched_skill_content`、`normalizer`）收敛到同一注入辅助。看到绿

## 5. 互斥命中：仅真冲突（命中数 > 1 且含互斥）才产出询问信号

- [ ] 5.1 Write failing tests：(a) **真冲突**——命中集合 > 1 个且含 `exclusive: true` 的 Skill 时，注入辅助不注入任何 L2 全文，并产出含候选 Skill 名的 `ask_signal`（D4 默认形态 `(system_prompt, AskSignal(candidates=[...]))`，断言 candidates 含两个候选名、system_prompt 不含任一 L2 全文）；(b) **单个 exclusive 独命中**——只命中一个 `exclusive: true` 的 Skill 时，**正常注入其 L2、`ask_signal` 为 None**（不询问，修复 origin bug）；(c) 多命中无互斥时 `ask_signal` 为 None 走单 L2 注入。看到红
- [ ] 5.2 Implement：注入辅助判定 `len(injectable 命中) > 1 且含 exclusive` → 不注入 L2 → 返回 `(system_prompt, AskSignal(candidates))`；否则（含单命中即便 exclusive）按 D2 注入首个 `injectable` 非互斥命中的 L2，`ask_signal=None`；`run_sync`/`run_stream`/`normalizer` 各自呈现（CLI 提示 / SSE 事件 / reply_func），不耦合具体交互通道。看到绿

## 6. 选定回灌语义（D5）

- [ ] 6.1 Write failing tests：携用户选定的 Skill 名再次进入注入辅助（如 `chosen_skill` 入参，或把选定名作为单一命中），断言对该选定 Skill **注入 L2 全文、`ask_signal` 为 None**；选定名若不过 `check_skill_access` / disabled 过滤则视为无效、不注入。看到红
- [ ] 6.2 Implement：注入辅助接受选定回灌（把命中集合收敛为单个候选，复用 D3 单命中正常注入分支，仍过 `injectable`）。看到绿

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归（尤其 `tests/test_skill_registry.py` 的 disabled 过滤、`tests/test_agent_loop.py` 的绑定门控既有用例）
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 7.3 `uv run mypy src` 无新增错误
