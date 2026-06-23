# e2e-reflection-lifecycle Specification

## Purpose
TBD - created by archiving change e2e-reflection-lifecycle. Update Purpose after archive.
## Requirements
### Requirement: reflection 触发与跨进程观测探针

apply SHALL 在写任何断言前，用最小探针在真实多进程 managed 栈下实测并记录：(a) reflection 的真实触发方式（scheduler，经 agent.yaml `reflection.enabled` + 短 `interval_seconds`）；(b) 可被反思的素材造法（organically 经 `/im/route` 对话产生轨迹/记忆，或经 agent 侧公开写入边界 seed——**不得 in-process mock、不得改 src**）；(c) 跨进程观测点（agent 侧 `agent_state.db` 的 `reflection_proposals` / `approval_requests` 物理路径与表结构，及 memory/skill 副作用落点）。探针 SHALL 诚实记录哪条 scenario 可不 mock 跑通、哪条需降级或 deferred。

#### Scenario: 探针确认无需 mock 即可端到端跑通

- **WHEN** apply 第一组任务在真实多进程栈下实测 reflection 触发、素材注入、审批、观测四点
- **THEN** 记录每点的真实路径结论；对任一 multi-process 下无法不 mock 跑通的 scenario，在 design / tasks 标注降级（更小切片）或 deferred，不强行 in-process mock

### Requirement: memory-maintenance 提案经真实审批后 apply e2e

SHALL 有一条 e2e 验证：reflection 生成的 memory-maintenance 提案，经真实 `/im/route` 路径由本人 `approve <proposal_id>` 审批后被 apply，且 agent 侧产生真实副作用。审批 SHALL 走 `/im/route`，不得直调 `approve_*_proposal` 函数。

审批所用的 `/im/route` 端点 SHALL 由测试**主动起一个 spawned managed agent route server**（已知 reserved 端口，复用 `_im_helpers.managed_agent_route_server` 的 `fleetent agent run --no-im --port` 方案、指向同一 agent home）提供；**不得**依赖对 node 拉起 agent 的 best-effort 端口扫描发现，**不得**在 gateway 不可自动发现时 `pytest.skip` 掉本条 approve→apply 路径。该 scenario MUST 真正执行至断言。

#### Scenario: memory 提案经 /im/route approve 后 applied 并改 agent 侧数据

- **WHEN** 在多进程 managed 栈下，reflection 生成（或经公开边界 seed）一条 memory-maintenance 提案（pending），测试经 spawned managed agent route server 的 `/im/route` 发 `approve <proposal_id>`
- **THEN** 跨进程读 agent 侧 `agent_state.db`，该 `reflection_proposals` 行 `status` 转为 applied 且 `applied_at` 已落，对应 memory item 副作用生效（如 `status=stale`）；本条不因 gateway 发现失败而 skip

### Requirement: low-risk mark_stale 提案 auto-apply e2e

SHALL 有一条 e2e 验证：当 agent.yaml `reflection.auto_apply.allow_low_risk=True` 时，risk=low 且 action=mark_stale 的 memory 提案**无需审批被直接 apply**。

#### Scenario: low-risk 提案无需审批直接 applied

- **WHEN** reflection-enabled agent 配 `auto_apply.allow_low_risk=True`，reflection 生成一条 risk=low / action=mark_stale 的 memory 提案
- **THEN** 该提案在无任何 `/im/route` 审批动作下即 applied（`applied_at` 已落），且不存在对应的 pending approval 等待

### Requirement: skill 提案经审批后写盘 e2e

SHALL 有一条 e2e 验证：reflection 生成的 skill 提案经审批后被 apply，SKILL.md 真写到 agent 可达的 skill 目录（`apply_skill_proposal` → `write_skill` + registry.reload）。若探针判定 skill 提案 organically 不可造，本 scenario SHALL 降级为"经 agent 侧公开写入边界 seed 一行 skill 提案 → 经 `/im/route` approve → 验 SKILL.md 落盘"（仍走真实 apply 路径），或在 tasks 标 deferred。

若本 scenario 经 `/im/route` approve 落地（非 deferred），其 `/im/route` SHALL 同样由 spawned managed agent route server（已知端口）提供，不得依赖端口扫描发现、不得因 gateway 不可发现而 skip。

#### Scenario: skill 提案 approve 后 SKILL.md 落盘

- **WHEN** 在多进程 managed 栈下存在一条 skill 提案（organically 生成或经公开边界 seed），测试经 spawned managed agent route server 的 `/im/route` 发 `approve <proposal_id>`
- **THEN** 该提案 `status` 转为 applied，且 agent 可达 skill 目录下出现对应 `SKILL.md` 文件

### Requirement: e2e 跑独立 slow lane，不进 per-merge 门禁

本 change 的多进程 reflection e2e SHALL 在独立 slow/nightly lane 运行（`make test-e2e`），**不**纳入 per-merge `make test-pr` 门禁。

#### Scenario: per-merge 门禁不含本 e2e

- **WHEN** 跑 per-merge 门禁 `make test-pr`
- **THEN** 不运行本 change 的多进程 reflection 生命周期 e2e（它们在 `make test-e2e` 独立 lane）

