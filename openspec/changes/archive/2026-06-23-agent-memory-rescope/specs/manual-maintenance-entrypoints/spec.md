## MODIFIED Requirements

### Requirement: Agent Memory edits use proposal lifecycle

任何平台面——维护命令面(`maintenance`)、专用 admin CLI(`memory agent *`)、以及平台 HTTP API(`/admin/memory/*`)——SHALL NOT 提供 agent memory 的直接编辑(create/update/archive)。agent memory 改动 SHALL 走 agent 侧 proposal/apply 生命周期(reflection 提议 → 审批门 → apply)。平台可读 agent memory 作投影,但不提供绕过治理的直写入口。

#### Scenario: 维护面不提供 agent memory 直接编辑

- **WHEN** operator 试图经 `maintenance` 维护面直接编辑 agent memory
- **THEN** 该操作不可用或被拒绝
- **AND** operator 被引导到 proposal/apply 生命周期

#### Scenario: 平台无专用 agent memory 直写入口

- **WHEN** 查看 `fleetent admin` 子命令与平台 HTTP API
- **THEN** 不存在 `memory agent create/update/archive` CLI,也不存在 `/admin/memory/agent` 直写端点

#### Scenario: agent memory 改动经 agent 侧生命周期

- **WHEN** 系统需要新增或修改一条 agent memory
- **THEN** 经 reflection 提议 → 审批 → apply 落地(`apply_agent_memory_proposal`),而非平台直写
