## Context

地基 harness（change A）已落地：`tests/e2e/conftest.py::managed_stack` 起单 tenant 单 agent 的真实多进程栈（platform + node + placed agent 子进程），`tests/e2e/_llm_stub.py` 提供确定性 LLM。本 change 在其上加 reflection 完整生命周期覆盖。

已核实的真实路径（`src/fleetent/reflection/reflection.py`、`scheduler.py`、`runtime/agent_app.py`、`governance/reflection_gate.py`）：

- **生成**：`run_reflection(scope, auto_policy=...)`（reflection.py:284）读 `observability.query_trace_events(TraceQuery(user_id=scope, ...))`（近 7 天）+ memory signals → `_generate_findings` → `generate_memory_maintenance_proposals` / `generate_skill_proposals` → 持久化 `reflection_proposals`，并经 `_create_proposal_approval_request` 写 `approval_requests`（proposal_id 作 approval_id + routing_key）。
- **触发**：`agent_app.py:390-403` 在 boot 时，若 agent.yaml `reflection.enabled=True`，调 `reflection_scheduler.start_reflection_scheduler(interval=interval_seconds, scope=agent.name, auto_policy=...)`；scheduler（`scheduler.py`）每 `interval` 秒 `await run_reflection(scope, auto_policy)`。**这是 managed 多进程下唯一真实触发**——平台侧 `platform/maintenance.py::run_reflection` 仅记一条 maintenance trace，是 stub，不调真实 reflection（已核实）。
- **auto-apply**：`auto_policy=AutoMaintenancePolicy(allow_low_risk=...)` 来自 agent.yaml `reflection.auto_apply.allow_low_risk`；`run_reflection` 对 memory 提案在生成后立即尝试 `apply_memory_maintenance_proposal(..., auto_policy=...)`，gate（`_auto_apply_allowed`）只放行 risk=low & action=mark_stale，其余留 pending。
- **审批**：用户经 `/im/route`（`agent_app.py:725` POST endpoint）发 `approve <proposal_id>` → `im_gateway/normalizer.route` → `approval_router.resolve_approval_request` → subject_type=memory_proposal 委派 `reflection_gate.resolve_reflection_proposal_action` → `approve_*_proposal` + `apply_*_proposal`。
- **数据落点**：`reflection_proposals` / `reflection_reports` / `approval_requests` 都在 agent 侧 **agent_state.db**（`_database()` 需 boot 时 `set_state_db`）。
- **副作用**：memory apply → 对应 memory item `status=stale`；skill apply（`apply_skill_proposal` → `write_skill` + registry.reload）→ skill 目录 `SKILL.md` 落盘。

## Goals / Non-Goals

**Goals**：端到端证明 reflection 提案在多进程 managed 栈下被真实生成、经真实 `/im/route` 审批、apply 真改 agent 侧数据（memory + skill 两类）+ low-risk auto-apply 真直接落地；helper 以新增方式提供，零 src 改动。

**Non-Goals**：不重构核心 `managed_stack`；不测 fan-out 投递原语（归 B）；不测 KB reflection report（`run_kb_reflection_report` 是只读报告，无 apply 闭环）；不测平台侧 `maintenance.run_reflection`（已确认是 stub）；不测 reflection 算法本身的 finding 质量（unit 层职责）。

## ⚠️ 头号可行性风险：multi-process 下绝不能 in-process mock

agent 在 managed 栈下是**独立子进程**——unit 那套 patch memory/skills/observability 在此完全不适用。四个落点必须用真实路径驱动，apply **第一组探针**逐条实测后才能定断言，不得假设：

1. **触发 reflection**：唯一真实入口是 scheduler（agent.yaml `reflection.enabled=True` + 极短 `interval_seconds`，如 0.5–1s，让它在测试窗口内自然 fire）。探针须确认：(a) e2e seed 的 agent 怎么带上 reflection 配置 —— 现有 `_seed_managed_agent` 不写 reflection，新 helper 须 seed 一个 reflection-enabled 的 agent.yaml 并 materialize；(b) scheduler 在子进程里真的起来并 fire（验 `reflection_reports` 出现新行）。
2. **造可被反思的素材**：`run_reflection` 读 `query_trace_events(user_id=scope)` + memory signals。探针定素材造法：
   - **memory-maintenance 提案**：依赖 memory signals / 轨迹 → 最可控的是先经 `/im/route` 跑几轮对话产生真实 trace + memory，或在 agent 侧 observability/memory 存储**经其公开写入边界 seed**（不 mock、不直改 src）。探针确认哪条能稳定催生 `mark_stale`（low-risk）提案。
   - **skill 提案**：`generate_skill_proposals` 来自 `_skill_opportunity_findings`（trace 中重复工作流模式）——organically 催生最难。探针重点验：能否经 seed 轨迹（重复 tool 调用模式）稳定催生一条 skill 提案；若不能，**降级**为"经 agent 侧公开写入边界 seed 一行 skill 提案 → 经 `/im/route` approve → 验 SKILL.md 落盘"的更小切片（仍是真实 apply 路径，只是素材 seed 而非 organically 生成），或标 deferred。
3. **驱动审批**：走真实 `/im/route` POST `approve <proposal_id>`（本人 principal），**不直调** `approve_*_proposal` 函数。探针确认 normalizer→approval_router→reflection_gate 委派在子进程里真的通。
4. **观测**：跨进程**只读** agent 侧 `agent_state.db`（`reflection_proposals.status` / `applied_at`、`approval_requests`）+ 文件系统副作用（memory item stale、skill 目录 SKILL.md），用 `wait_for_condition` 轮询。探针先定位 agent_state.db 的真实物理路径（`<home>/agents/<name>/...`）与表结构。

## Decisions

- **审批走真实 `/im/route`，不直调 apply 函数**：这正是 e2e 要抓的接线回归（scheduler→生成→approval_requests→normalizer→reflection_gate→apply 全链）。
- **helper 独占 `_reflection_helpers.py`，不改 `managed_stack` / conftest 核心**：reflection-enabled agent seed、素材注入、审批发送、跨进程观测全放该文件，并行波 B/C/D 不碰 → 零 `conftest.py` 合并冲突。复用 `managed_stack` 的起栈步骤组件（`child_env` / `running_process` / `wait_for_*` / `_register_node`），但以新 fixture 形态组合，不就地改核心 fixture。
- **A4b/fan-out 边界归 B**：审批投递经 `/im/route` 这条真实路径触达，但本 change **不**断言 `notify_user` fan-out 原语本身（多渠道扇出语义）；只断言"提案被审批且 apply 生效"。fan-out 原语由 B（`e2e-im-inbound-approval`）独占覆盖。
- **素材 seed vs organically 生成由探针定**：优先 organically（经 `/im/route` 对话产生真实 trace/memory），不可行则降级为经 agent 侧公开写入边界 seed（仍非 mock、非改 src）。降级范围写进 tasks 第 1 组结论。

## Risks / Trade-offs

- **scheduler 在子进程里 fire 时序不确定** → 极短 interval + `wait_for_condition` 轮询 `reflection_reports`/`reflection_proposals` 出现；超时给足（e2e slow lane 可接受）。
- **skill 提案 organically 难造** → 探针判定后降级为 seed 提案行（见上），诚实记入 tasks。
- **素材注入若找不到不 mock 的公开边界** → 对应 scenario 标 deferred，design 与 tasks 同步注明，不强行 in-process mock。
- **起 reflection-enabled agent + 跑对话增加栈时长** → e2e 在 slow lane，可接受。
