## MODIFIED Requirements

### Requirement: Shared Memory edits use proposal lifecycle

任何平台面——维护命令面(`maintenance`)、专用 admin CLI(`memory shared *`)、以及平台 HTTP API(`/admin/memory/*`)——SHALL NOT 提供共享记忆的直接编辑(create/update/archive)。共享记忆改动 SHALL 走 agent 侧 proposal/apply 生命周期(reflection 提议 → 审批门 → apply)。平台可读共享记忆作投影,但不提供绕过治理的直写入口。

#### Scenario: 维护面不提供共享记忆直接编辑

- **WHEN** operator 试图经 `maintenance` 维护面直接编辑共享记忆
- **THEN** 该操作不可用或被拒绝
- **AND** operator 被引导到 proposal/apply 生命周期

#### Scenario: 平台无专用共享记忆直写入口

- **WHEN** 查看 `fleetent admin` 子命令与平台 HTTP API
- **THEN** 不存在 `memory shared create/update/archive` CLI,也不存在 `/admin/memory/shared` 直写端点

#### Scenario: 共享记忆改动经 agent 侧生命周期

- **WHEN** 系统需要新增或修改一条共享记忆
- **THEN** 经 reflection 提议 → 审批 → apply 落地(`apply_shared_memory_proposal`),而非平台直写
