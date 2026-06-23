## MODIFIED Requirements

### Requirement: memory-maintenance 提案经真实审批后 apply e2e

SHALL 有一条 e2e 验证：reflection 生成的 memory-maintenance 提案，经真实 `/im/route` 路径由本人 `approve <proposal_id>` 审批后被 apply，且 agent 侧产生真实副作用。审批 SHALL 走 `/im/route`，不得直调 `approve_*_proposal` 函数。

审批所用的 `/im/route` 端点 SHALL 由测试**主动起一个 spawned managed agent route server**（已知 reserved 端口，复用 `_im_helpers.managed_agent_route_server` 的 `fleetent agent run --no-im --port` 方案、指向同一 agent home）提供；**不得**依赖对 node 拉起 agent 的 best-effort 端口扫描发现，**不得**在 gateway 不可自动发现时 `pytest.skip` 掉本条 approve→apply 路径。该 scenario MUST 真正执行至断言。

#### Scenario: memory 提案经 /im/route approve 后 applied 并改 agent 侧数据

- **WHEN** 在多进程 managed 栈下，reflection 生成（或经公开边界 seed）一条 memory-maintenance 提案（pending），测试经 spawned managed agent route server 的 `/im/route` 发 `approve <proposal_id>`
- **THEN** 跨进程读 agent 侧 `agent_state.db`，该 `reflection_proposals` 行 `status` 转为 applied 且 `applied_at` 已落，对应 memory item 副作用生效（如 `status=stale`）；本条不因 gateway 发现失败而 skip

### Requirement: skill 提案经审批后写盘 e2e

SHALL 有一条 e2e 验证：reflection 生成的 skill 提案经审批后被 apply，SKILL.md 真写到 agent 可达的 skill 目录（`apply_skill_proposal` → `write_skill` + registry.reload）。若探针判定 skill 提案 organically 不可造，本 scenario SHALL 降级为"经 agent 侧公开写入边界 seed 一行 skill 提案 → 经 `/im/route` approve → 验 SKILL.md 落盘"（仍走真实 apply 路径），或在 tasks 标 deferred。

若本 scenario 经 `/im/route` approve 落地（非 deferred），其 `/im/route` SHALL 同样由 spawned managed agent route server（已知端口）提供，不得依赖端口扫描发现、不得因 gateway 不可发现而 skip。

#### Scenario: skill 提案 approve 后 SKILL.md 落盘

- **WHEN** 在多进程 managed 栈下存在一条 skill 提案（organically 生成或经公开边界 seed），测试经 spawned managed agent route server 的 `/im/route` 发 `approve <proposal_id>`
- **THEN** 该提案 `status` 转为 applied，且 agent 可达 skill 目录下出现对应 `SKILL.md` 文件
