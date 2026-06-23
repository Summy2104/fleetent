## 1. 可行性探针（先于任何断言；不 mock、不改 src）

- [ ] 1.1 **触发探针**：用既有 `managed_stack` 起栈的方式，seed 一个 `reflection.enabled=True` + 极短 `interval_seconds`（如 0.5–1s）的 agent.yaml（经 materialize），确认 scheduler 在 agent 子进程里真的起来并 fire——验 agent 侧 `agent_state.db` 出现新 `reflection_reports` 行。记录：reflection 配置怎么进 seed 的 agent.yaml、scheduler fire 的可观测信号。
- [ ] 1.2 **素材探针**：实测怎么不 mock 地造出可被反思的素材——优先经 `/im/route` 跑几轮对话产生真实 trace/memory；若不稳定，定位 agent 侧 observability/memory 的公开写入边界做 seed。记录：哪条素材能稳定催生 memory `mark_stale`（low-risk）提案、skill 提案能否 organically 造（不能则降级为经公开边界 seed 一行 skill 提案）。
- [ ] 1.3 **观测探针**：定位 agent 侧 `agent_state.db` 物理路径（`<home>/agents/<name>/...`）与 `reflection_proposals` / `approval_requests` 表结构、`applied_at` 字段；定位 memory item stale 副作用与 skill 目录 SKILL.md 落点。记录跨进程**只读**观测姿势（`wait_for_condition` 轮询）。
- [ ] 1.4 **审批探针**：实测经 `/im/route` POST `approve <proposal_id>`（本人 principal）→ normalizer → approval_router → reflection_gate 委派在子进程里真的通（先用一条已存在的 pending 提案验）。
- [ ] 1.5 **结论 + 降级裁定**：汇总四点，逐条裁定 memory-apply / auto-apply / skill-apply 三 scenario 是否可不 mock 跑通；对不可行的明确降级（更小切片）或标 deferred，写回本 tasks 与 design。**任何 in-process mock 的冲动 = 停下重想**。

## 2. helper 脚手架 `tests/e2e/_reflection_helpers.py`（本 change 独占）

- [ ] 2.1 **测试（红）**：在 `tests/e2e/_reflection_helpers.py` 写 seed reflection-enabled agent + 起栈的组合逻辑（复用 `child_env` / `running_process` / `wait_for_*` / `_register_node`，**不改 `conftest.py::managed_stack`**）。先写一个"reflection-enabled agent 就绪 + scheduler fire 后 `reflection_reports` 出现新行"的最小测试，跑见红。
- [ ] 2.2 **实现（绿）**：实现该 helper（agent.yaml 带 reflection 配置 materialize + 起栈 + 跨进程读 agent_state.db 的轮询工具）。跑见绿。

## 3. E2E-1 memory-maintenance 提案 → /im/route approve → apply

- [ ] 3.1 **测试（红）**：用 helper 起 reflection-enabled agent（auto_apply 关），按探针结论注入素材催生一条 pending memory-maintenance 提案 → 经 `/im/route` 发 `approve <proposal_id>` → 跨进程断言 `reflection_proposals.status=applied` + `applied_at` 已落 + 对应 memory item `status=stale`。先跑见红。
- [ ] 3.2 **绿**：让它过（若红，定位 scheduler/生成/approval_requests/normalizer/reflection_gate/apply 哪段断——这正是 e2e 要抓的接线回归）。

## 4. E2E-2 low-risk mark_stale auto-apply

- [ ] 4.1 **测试（红）**：用 helper 起 `reflection.auto_apply.allow_low_risk=True` 的 agent，注入催生 risk=low / action=mark_stale 提案的素材 → 断言该提案**无任何审批动作**即 `applied_at` 已落、不存在对应 pending approval。先跑见红。
- [ ] 4.2 **绿**：让它过。

## 5. E2E-3 skill 提案 → approve → SKILL.md 落盘

> 范围以 task 1.5 结论为准：organically 生成优先；不可行则降级为经 agent 侧公开写入边界 seed 一行 skill 提案（仍走真实 `/im/route` approve + apply），或本组标 deferred 并在此注明。

- [ ] 5.1 **测试（红）**：用 helper 造出一条 skill 提案（organically 或 seed）→ 经 `/im/route` 发 `approve <proposal_id>` → 断言 `reflection_proposals.status=applied` + agent 可达 skill 目录出现对应 `SKILL.md`。先跑见红。
- [ ] 5.2 **绿**：让它过（验证 `apply_skill_proposal` → `write_skill` + registry.reload 端到端通，含 12ed93b5 修复点）。

## 6. 收尾 + lane

- [ ] 6.1 `make test-e2e` 跑这批（含 helper + 3 测试）；确认**不在** `make test-pr` 里。
- [ ] 6.2 `make test-pr` 仍全绿（本 change 纯 test 侧、不碰 src，对照 main 基线无新增失败）。
- [ ] 6.3 边界自检：仅新增 `tests/e2e/_reflection_helpers.py` + 本 change 的 test 文件；**未改** `tests/e2e/conftest.py::managed_stack` / conftest 核心、未改任何 src；与 B 不重叠 fan-out 原语测试。如确需改核心 fixture 或 src，停下说明（违反并行纪律）。
