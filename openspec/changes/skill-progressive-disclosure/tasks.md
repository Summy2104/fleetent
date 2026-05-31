## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 SK2 已合入：`_index` 为 `dict[str, SkillEntry]`，`SkillEntry` 含 `description`，可作 L1 摘要数据源（skill_registry.py 行 20-31）
- [ ] 1.2 核实三处注入点现状：`run_sync()`（行 479，注入调用行 496）与 `run_stream()`（行 505，注入调用行 531）共用 `agent_loop._matched_skill_content`（行 231，内含 `match`+`check_skill_access`+`load` 的 agent 绑定门控）；`im_gateway/normalizer.py`（行 81-82）独立内联同一套逻辑；`run()`（行 299）只收预构建 messages、不做注入。确认改为「L1（按 agent 过滤）始终 + L2 命中」后的增量行为
- [ ] 1.3 确认 `match(user_input, disabled_skills=None)`（行 94）/ `load(name)`（行 142）/ `list_skills()`（行 147）对外契约与 `check_skill_access` 签名，确认新增 `l1_summary(...)` 不改既有契约

## 2. L1 摘要产出（skill_registry.l1_summary，按 agent 过滤）

- [ ] 2.1 Write failing tests for `l1_summary(allowed_skills, blocked_skills, disabled_skills=None)`：`tests/test_skill_registry.py` 断言——清单仅含**当前 agent 可用且启用**的 Skill（过 `check_skill_access` ∧ enabled ∧ ¬disabled_skills）；不在 `allowed_skills`/被 `blocked_skills`/被 `disabled_skills`/`enabled_by_default=false` 的 Skill **不**出现在清单中；可注入项为空时返回空串；保留项渲染含其 `name` 与 `description`；skills 目录隔离到 `tmp_path`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `l1_summary(allowed_skills, blocked_skills, disabled_skills=None) -> str`：遍历 `_index`，按 `injectable` 同源条件（agent 绑定 ∧ enabled ∧ ¬disabled_skills，见 design D4）过滤后渲染「名称+描述」清单，不改 `match`/`load`/`list_skills`。运行 `uv run pytest -x -q` 看到绿

## 3. 单一共享注入函数（agent_loop：L1 始终 + L2 命中，三处入口共用）

- [ ] 3.1 Write failing tests：命中某 Skill 且过门控时，共享注入函数（如 `_skill_injection(user_input, allowed_skills, blocked_skills)`）产出的内容同时包含 L1 清单（该 Skill 名）与该 Skill 的 L2 全文；`run_sync()`（行 496）与 `run_stream()`（行 531）经它构造的 system prompt 同理。mock `get_async_client_and_config`，skills 目录隔离到 `tmp_path`。看到红
- [ ] 3.2 Implement：把 `_matched_skill_content` 扩展/抽出为单一共享注入函数，先拼 L1 清单（`l1_summary`，按 agent 过滤、非空时），命中且过 `check_skill_access` 再追加 L2 全文，L1/L2 分段拼接；`run_sync` / `run_stream` 改调它。看到绿
- [ ] 3.3 Write failing tests：未命中任何关键词时 system prompt 仍包含 L1 清单（当前 agent 可用且启用的 Skill 名），但不包含任何 Skill 的 L2 全文正文；且 L1 清单中**不**出现该 agent 不可用（未在 allowed / 被 blocked / 被 disabled）的 Skill。看到红
- [ ] 3.4 Implement 使未命中路径注入（过滤后的）L1、不注入 L2。看到绿

## 4. 三注入点收敛（含 IM 渠道 normalizer）

- [ ] 4.1 Write failing tests：`im_gateway/normalizer.py` 注入路径与 `run_sync`/`run_stream` 行为一致——命中且过门控时 IM 渠道注入的 system 内容同时含 L1 清单与 L2 全文，未命中时仍含（过滤后的）L1 清单。mock LLM 与 session，skills 目录隔离到 `tmp_path`。看到红
- [ ] 4.2 Implement：`im_gateway/normalizer.py`（行 81-82）改调同一共享注入函数，移除其内联的 `match`+`check_skill_access`+`load`，使 L1/L2 改造覆盖三处入口、不漏 IM 渠道。看到绿

## 5. L3 边界（附属资源不进 prompt）

- [ ] 5.1 Write failing tests：某 Skill 的 SKILL.md 引用了附属文件（如 `references/x.md`），命中注入 L2 后，system prompt 不包含该附属文件的内容（只含 SKILL.md 正文）。看到红
- [ ] 5.2 Implement / 确认：注入链只读 `load()`（SKILL.md 正文），不读取任何被引用的附属文件。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归（既有 skill_registry、agent_loop、normalizer 用例仍绿）。**显式核对回归风险**：本 change 改为「始终注入（过滤后的）L1 清单」会让每个请求的 system prompt 在原内容外多出 L1 段，现有 `tests/test_agent_loop.py` / normalizer 测试中断言 system prompt 精确内容 / 长度 / 不含额外段的用例可能因此回归——逐个核对并按新基线（含 L1 清单）更新断言，确认变更是预期而非缺陷
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
