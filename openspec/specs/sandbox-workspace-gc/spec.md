# sandbox-workspace-gc Specification

## Purpose
TBD - created by archiving change sandbox-isolation-foundation. Update Purpose after archive.
## Requirements
### Requirement: session scope workspace 随会话过期整目录回收

workspace GC SHALL 在会话按 TTL 过期被清理时，回收该会话对应的 `session` scope workspace 宿主目录（整目录删除）。回收 MUST 复用既有会话过期触发点（`session-ttl-cleanup` / `internal-session-maintenance`），但作用对象为 `workspaces` 根下该会话的子目录，而非 `SESSIONS_DIR`。容器若仍存活，回收 MUST 先经既有释放路径销毁容器再删目录，避免删除正被 bind mount 的活跃目录。

#### Scenario: 会话过期回收其 workspace 目录
- **WHEN** 一个会话按 TTL 过期并被会话清理流程处理
- **THEN** 该会话的 `session` scope workspace 宿主子目录被整目录删除，目录内 `uploads/` 与产物随之回收，不残留明文敏感上传

#### Scenario: 未过期会话的目录不被回收
- **WHEN** 会话仍存活或未达 TTL
- **THEN** 其 workspace 宿主目录及内容保持不动

### Requirement: agent scope workspace 按 mtime 目录内清理

对 `agent` scope workspace（多会话共享同一宿主目录），workspace GC MUST NOT 整目录删除（会误删跨会话复用的依赖与数据），SHALL 按子项的最近修改时间（mtime）在目录内清理超过保留期未使用的内容，目录本身与近期使用的内容 MUST 保留。

#### Scenario: 仅清理超保留期的陈旧内容
- **WHEN** `agent` scope workspace 目录内既有超过保留期未修改的文件，也有近期使用的文件
- **THEN** 仅超保留期的文件被清理，近期使用的文件与目录本身保留

### Requirement: 回收前路径围栏校验

workspace GC 在删除任何宿主路径前 MUST 经与 workspace 创建时同源的 `is_blocked_mount` 护栏校验，并确认解析（realpath）后的待删路径落在 `workspaces` 根之内；命中敏感路径或越出根目录时 MUST 拒绝删除并记录一条护栏日志，绝不在 `workspaces` 根之外执行删除。

#### Scenario: 越界或敏感路径拒绝删除
- **WHEN** GC 解析出的待删路径经 realpath 后落在 `workspaces` 根之外，或命中 `is_blocked_mount` 敏感路径（如经符号链接逃逸）
- **THEN** 该删除被拒绝并记录护栏日志，不执行任何文件系统删除

