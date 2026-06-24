## MODIFIED Requirements

### Requirement: tool_context 定位 scope 容器

文件工具 SHALL 接受 tool_context（session_id/agent_name），据此定位与 run_code 一致的 scope 容器；无 tool_context 时使用与 run_code 一致的默认 key。Agent runtime 下，host workspace root SHALL be `<agent-home>/data/workspaces/`，not `FLEETENT_HOME/data/workspaces/`.

#### Scenario: 同 session 复用容器
- **WHEN** 同一 session 先后调用 run_code 与文件工具
- **THEN** 二者操作同一 scope 容器的同一 `/workspace`

#### Scenario: Agent runtime workspace is agent-scoped
- **WHEN** agent `support` invokes file tools or run_code with scope key `S1`
- **THEN** host workspace directory is under `<agent-home>/data/workspaces/S1`
- **AND** no workspace directory is created under `FLEETENT_HOME/data/workspaces`

### Requirement: sandbox 不可用或后端不支持挂载时降级为宿主执行加路径围栏

当 sandbox 不可用（后端不可用或 mode=off），或选定后端未声明 `workspace_mount` capability 时，文件工具 SHALL 降级为宿主执行，但路径经规范化 + workspace 根前缀判定限制在宿主 workspace 目录内；越界路径 MUST 被拒绝。降级取宿主视图与 IM 附件暂存（写宿主 workspace）保持一致；此时 `run_code` 的容器内 `/workspace` 与文件工具视图分歧为已知限制（见 sandbox-workspace-mount 降级条款）。

#### Scenario: 降级仍锁 workspace
- **WHEN** 后端不可用（或不支持挂载）且文件工具收到越界路径
- **THEN** 路径围栏拒绝该路径，不读写 workspace 外宿主文件

#### Scenario: 不支持挂载的后端附件仍可读
- **WHEN** 选定后端不支持挂载，IM 附件已暂存到 `<agent-home>/data/workspaces/<scope>/uploads/`
- **THEN** 文件工具以宿主围栏路径读到附件内容
