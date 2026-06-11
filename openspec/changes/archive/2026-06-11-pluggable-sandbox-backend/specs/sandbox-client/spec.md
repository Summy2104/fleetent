# sandbox-client（delta）

> 本 delta 还清技术债：主 spec 仍是项目早期 microsandbox 时代的陈旧版本（多个归档 change 的归属说明所指）。本次将其重写为后端中立的权威表述，过时需求删除，被其他能力 spec 承接的需求迁出。

## MODIFIED Requirements

### Requirement: Tool execution in sandbox
The system SHALL route shell/code execution tool calls through the canonical sandbox execution surface, which is backed by the configured pluggable backend (Docker or microsandbox).

#### Scenario: Shell command execution
- **WHEN** agent calls a sandboxed tool with a command
- **THEN** the command is executed inside the selected backend's isolated workspace via the backend abstraction's `exec`, returning stdout/stderr/exit_code

#### Scenario: File state persists within session
- **WHEN** agent writes a file in step 1 and reads it in step 2 of the same session
- **THEN** the file is present in step 2

### Requirement: Cross-session isolation
Workspaces from different sessions SHALL be fully isolated, regardless of the selected backend.

#### Scenario: Session isolation
- **WHEN** session A writes `secret.txt` to its workspace
- **THEN** session B cannot read `secret.txt` (separate container on the Docker backend; separate microVM on the microsandbox backend)

### Requirement: Sandbox failure handling
The system SHALL handle backend connectivity failures gracefully.

#### Scenario: Selected backend unreachable
- **WHEN** a sandboxed tool execution fails because the selected backend is unavailable (Docker daemon down, or msb server unreachable)
- **THEN** the tool returns an error message to the agent; the agent decides whether to retry or inform the user

## REMOVED Requirements

### Requirement: Per-session workspace lifecycle
**Reason**: 陈旧的 microsandbox 时代表述（「会话开始即建、会话结束即销」）与现实不符——工作区由 `SandboxManager` 按 scope 惰性获取与回收。
**Migration**: 工作区生命周期由 `sandbox-lifecycle` spec（scope 模型：session 复用/会话结束销毁、agent 跨会话复用/闲置回收）权威定义。

### Requirement: Host connectivity
**Reason**: 陈旧的 microsandbox 时代表述——`host.docker.internal` 固定连接方式已不存在。
**Migration**: microsandbox 后端连接方式（`sandbox.microsandbox.server_url` 配置 + `MSB_API_KEY` 环境变量）由 `microsandbox-backend` spec 定义；Docker 后端经本机 CLI，无网络连接配置。
