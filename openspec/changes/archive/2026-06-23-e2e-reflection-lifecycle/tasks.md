## 1. 可行性探针（先于任何断言；不 mock、不改 src）

- [x] 1.1 **触发探针**：已确认 `agent_store.create_agent(..., config_overrides={"reflection": ...})` → `materialize.write_home(...)` 可把 `reflection.enabled=True` + `interval_seconds=0.5` seed 进 managed agent；agent healthy 后，scheduler 会在子进程内真实写出 `reflection_reports`。
- [x] 1.2 **素材探针**：已确认可经 agent-side observability 公开写入边界 seed 两条重复 `task_pattern` trace，scheduler 会 organically 产出 pending skill proposal。memory 侧未找到可由 `run_reflection()` 稳定生成并可 apply 的 `mark_stale` proposal：当前 reflection 生成的 memory proposal 形态不覆盖该闭环，因此 memory / auto-apply 场景降级。
- [x] 1.3 **观测探针**：已定位 agent 侧 DB 路径为 `agents/<agent>/data/<tenant>/<agent>/agent_state.db`；跨进程只读轮询 `reflection_reports` / `reflection_proposals` / `memory_items` 可稳定观测 scheduler 结果与 proposal 持久化。
- [x] 1.4 **审批探针**：deferred。当前 managed e2e harness 对 agent loopback `/im/route` gateway 无稳定外部发现路径（node forwarder 仅转 `/chat` / `/ws`，agent gateway port 未持久暴露），因此无法在不改 src / 核心 fixture 的前提下稳定外打 `/im/route approve <id>`。
- [x] 1.5 **结论 + 降级裁定**：最终保留两条真实通过场景：`scheduler -> reflection_reports`、`scheduler -> pending skill proposal`。`memory-apply` / `low-risk auto-apply` / `skill-apply via /im/route` 明确 deferred，并在 e2e 中以 `skip` 或不覆盖的方式诚实降级。

## 2. helper 脚手架 `tests/e2e/_reflection_helpers.py`（本 change 独占）

- [x] 2.1 **测试（红）**：已写最小红灯测试 `test_reflection_enabled_managed_agent_emits_scheduler_report`。
- [x] 2.2 **实现（绿）**：已实现 `tests/e2e/_reflection_helpers.py` 的 reflection-enabled managed stack helper、agent-side script seed、`agent_state.db` 轮询工具；最小测试转绿。

## 3. E2E-1 memory-maintenance 提案 → /im/route approve → apply

- [x] 3.1 **测试（红）**：已写 memory `mark_stale` proposal 经 `/im/route approve` 的期望测试，并确认在当前 harness 下因 gateway 不可外探而无法稳定满足前置条件。
- [x] 3.2 **绿**：deferred 为 `skip`。原因同 1.4：managed 多进程 harness 下无法在不改 src / 核心 fixture 的前提下稳定命中 agent `/im/route`。

## 4. E2E-2 low-risk mark_stale auto-apply

- [x] 4.1 **测试（红）**：经探针确认当前 `run_reflection()` 无稳定公开路径生成可 auto-apply 的 `mark_stale` proposal，故本组不再继续写误导性红灯。
- [x] 4.2 **绿**：deferred。auto-apply 场景保留到后续实现补齐 memory proposal 生成形态或暴露可测触发边界后再恢复。

## 5. E2E-3 skill 提案 → approve → SKILL.md 落盘

> 范围以 task 1.5 结论为准：organically 生成优先；不可行则降级为经 agent 侧公开写入边界 seed 一行 skill 提案（仍走真实 `/im/route` approve + apply），或本组标 deferred 并在此注明。

- [x] 5.1 **测试（红）**：已写并跑通 `test_reflection_scheduler_generates_pending_skill_proposal_from_repeated_task_pattern`，确认 skill proposal 可由 scheduler organically 生成；`/im/route approve` 子场景因 1.4 的 gateway 可观测性限制 deferred。
- [x] 5.2 **绿**：部分完成。pending skill proposal 生成已绿；`apply_skill_proposal` / `SKILL.md` 落盘闭环 deferred，待 managed `/im/route` 可稳定外打后恢复。

## 6. 收尾 + lane

- [ ] 6.1 `make test-e2e` 跑这批（含 helper + 3 测试）；确认**不在** `make test-pr` 里。
- [ ] 6.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [x] 6.3 边界自检：仅新增 `tests/e2e/_reflection_helpers.py` + 本 change 的 test 文件；**未改** `tests/e2e/conftest.py::managed_stack` / conftest 核心、未改任何 src；与 B 不重叠 fan-out 原语测试。
