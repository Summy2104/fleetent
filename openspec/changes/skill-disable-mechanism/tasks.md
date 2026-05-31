## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实范围划界：builtin-skills 已覆盖 `disabled_skills` 全局禁用 + `enabled_by_default` 默认态；agent-skill-binding 已覆盖 per-agent 白/黑名单。确认本 change 只做 `enabled` 自禁用 + 禁用来源 trace，不重复二者
- [ ] 1.2 核实 SK2 frontmatter 解析路径（skill_registry.py 行 39-56），确认 `enabled` 字段可经 `bool(frontmatter.get("enabled", True))` 填充 `SkillEntry`
- [ ] 1.3 确认 `log_run` 签名（eval_logger.py 行 20），新增末位可选 kw（`disabled_skills_trace=None`）即向后兼容；**核实注入/trace 断链事实**：注入在 `run_sync()`（行 408-415）/ `run_stream()`（行 451-453），`log_run` 调用在 `run()`（行 389）/ `run_stream()`（行 589），`run_sync` 经 `run()` 委托且 `run()` 当前无参数承载禁用来源——确认需给 `run()` 新增 `disabled_skills_trace` 透传参数（类比 `agent_name`）；确认 SK3 的 `match_all` 候选中间产物结构以便叠加禁用来源标注；确认 builtin-skills / agent-skill-binding 的禁用判定接口形态以便叠加来源识别

## 2. frontmatter enabled 自禁用字段

- [ ] 2.1 Write failing tests：含 `enabled: false` 的 SKILL.md 扫描后 `SkillEntry.enabled` 为假；未声明时缺省为真。`tests/test_skill_registry.py`。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement：`SkillEntry` 新增 `enabled: bool = True`，`scan` 处由 frontmatter 填充。看到绿

## 3. enabled 硬关停优先于默认态

- [ ] 3.1 Write failing tests：`enabled: false` 的 Skill 被用户输入命中关键词时不出现在对外 `match` 结果、不被注入；但 SK3 的 `match_all` 候选中间产物中**保留**该项并标注「命中但禁用 + 来源 frontmatter_disabled」（供 trace）；`enabled_by_default: true` 但 `enabled: false` 时仍被禁用（硬关停优先于默认态）；`load` 仍可按名取原文。看到红
- [ ] 3.2 Implement：禁用过滤叠加 `enabled is False`——对外 `match`/注入链不返回禁用项，`match_all` 候选保留「命中但禁用 + 来源」标注（不在遍历里 `continue` 丢弃信息）；`load` 不受 `enabled` 约束。看到绿

## 4. 禁用来源写入 trace

- [ ] 4.1 Write failing tests for `log_run` 新字段：默认 None 时 trace 不含该字段（向后兼容）；传入 `{skill: 来源}` 时写入。`tests/test_eval_logger.py`。看到红
- [ ] 4.2 Implement：`log_run` 新增末位可选字段 `disabled_skills_trace: dict[str, str] | None = None`，默认 None 向后兼容、非 None 写入 entry。看到绿
- [ ] 4.3 Write failing tests for `run()` 新增透传参数（解决断链）：`run(..., disabled_skills_trace={...})` 时该 dict 出现在 `run()` 末尾 `log_run` 写出的 trace；默认 None 时现有 `run()` 调用方行为不变（向后兼容）。mock `get_async_client_and_config`。看到红
- [ ] 4.4 Implement：给 `run()` 新增参数 `disabled_skills_trace: dict[str, str] | None = None`，透传给末尾 `log_run`（类比 `agent_name`），不改其余 `run()` 契约。看到绿
- [ ] 4.5 Write failing tests：`run_sync()` 注入时跳过被 `enabled: false` 禁用且本可命中的 Skill，经 `run()` 透传后该次运行 trace 含 `{skill: frontmatter_disabled}`；`run_stream()` 路径在同一函数体内就近收集并传入行 589 的 `log_run`，trace 同样含来源；无禁用的正常运行不写该字段。mock `get_async_client_and_config`，skills 目录隔离 `tmp_path`。看到红
- [ ] 4.6 Implement：`run_sync()` 收集被禁用 Skill 及来源 → 调 `run(..., disabled_skills_trace=...)` 透传；`run_stream()` 就近收集 → 传入行 589 的 `log_run`；来源标识对齐 design（frontmatter_disabled 等）。看到绿

## 5. 与既有禁用来源叠加（不重复实现）

- [ ] 5.1 Write failing tests：当 builtin-skills / agent-skill-binding 的判定可用时，被这些来源禁用的 Skill 在 trace 中记为对应来源（`config_disabled` / `default_disabled` / `agent_blocked`）；本 change 不重新判定这些来源，仅识别并记录。看到红
- [ ] 5.2 Implement：叠加裁决按 OR 语义汇总来源；第 2-4 条来源复用并行 change 的判定结果（未合入时该来源恒不命中），仅第 1 条由本 change 判定。看到绿

## 6. 收尾

- [ ] 6.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 6.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 6.3 `uv run mypy src` 无新增错误
