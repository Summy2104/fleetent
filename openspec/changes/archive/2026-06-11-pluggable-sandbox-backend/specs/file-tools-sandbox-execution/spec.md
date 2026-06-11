# file-tools-sandbox-execution（delta）

## MODIFIED Requirements

### Requirement: 文件工具经容器执行操作 workspace

当 sandbox 可用且选定后端声明 `workspace_mount` capability 时，5 个文件工具（read_file/write_file/edit_file/search_content/search_files）SHALL 经 `SandboxManager` 取得 scope 容器并通过后端 `exec` 在容器内执行 shell 命令操作 `/workspace`，而非在宿主进程直接读写。

#### Scenario: read_file 走容器
- **WHEN** sandbox 可用、后端支持挂载，agent 调用 read_file 读 workspace 内文件
- **THEN** 文件内容经容器内命令读取并返回，宿主进程不直接 open 该路径

#### Scenario: write_file 走容器
- **WHEN** sandbox 可用、后端支持挂载，agent 调用 write_file 写 workspace 内文件
- **THEN** 内容经容器内命令写入，落在容器 `/workspace`（= 宿主 workspace 目录）

## ADDED Requirements

### Requirement: sandbox 不可用或后端不支持挂载时降级为宿主执行加路径围栏

当 sandbox 不可用（后端不可用或 mode=off），或选定后端未声明 `workspace_mount` capability 时，文件工具 SHALL 降级为宿主执行，但路径经规范化 + workspace 根前缀判定限制在宿主 workspace 目录内；越界路径 MUST 被拒绝。降级取宿主视图与 IM 附件暂存（写宿主 workspace）保持一致；此时 `run_code` 的容器内 `/workspace` 与文件工具视图分歧为已知限制（见 sandbox-workspace-mount 降级条款）。

#### Scenario: 降级仍锁 workspace
- **WHEN** 后端不可用（或不支持挂载）且文件工具收到越界路径
- **THEN** 路径围栏拒绝该路径，不读写 workspace 外宿主文件

#### Scenario: 不支持挂载的后端附件仍可读
- **WHEN** 选定后端不支持挂载，IM 附件已暂存到宿主 workspace，agent 调用 read_file 读取
- **THEN** 文件工具以宿主围栏路径读到附件内容

## REMOVED Requirements

### Requirement: docker 不可用时降级为宿主执行加路径围栏
**Reason**: 降级条件从「docker 不可用」泛化为「后端不可用或后端不支持挂载」；围栏行为不变。
**Migration**: 由本 delta 的 ADDED 需求「sandbox 不可用或后端不支持挂载时降级为宿主执行加路径围栏」承接。
