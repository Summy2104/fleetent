# sandbox-workspace-mount（delta）

## MODIFIED Requirements

### Requirement: Workspace 按 scope 映射进容器

在声明 `workspace_mount` capability 的后端（Docker）上，系统 SHALL 为每个 scope（`session` 粒度用 session_id、`agent` 粒度用 agent_name，复用 `SandboxManager` 现有 Scope）维护独立的宿主 workspace 子目录，并在创建容器时通过 bind mount 映射到容器内固定挂载点 `/workspace`。同一 scope 的容器复用时 MUST 映射到同一宿主子目录。

后端未声明 `workspace_mount` 时，获取工作区 MUST 不传递任何宿主挂载（容器内 `/workspace` 为实例本地目录，不与宿主共享）；文件工具按 `file-tools-sandbox-execution` 的降级条款走宿主围栏执行。此时 `run_code` 容器内视图与文件工具宿主视图分歧为已知限制，降级 MUST 记录一条说明日志。

#### Scenario: session scope 映射
- **WHEN** Docker 后端下以 session scope 为某 session_id 获取容器
- **THEN** 宿主 `data/workspaces/<session_id>/` 被 bind mount 到容器 `/workspace`

#### Scenario: 同 scope 复用同目录
- **WHEN** Docker 后端下同一 scope key 的容器被复用或重建
- **THEN** 映射到的宿主 workspace 子目录与首次一致

#### Scenario: 不支持挂载的后端不传宿主路径
- **WHEN** 选定后端未声明 `workspace_mount`，为任一 scope 获取工作区
- **THEN** 创建调用不携带宿主挂载路径，记录一条降级说明日志，工作区仍可正常创建与执行
