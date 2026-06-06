# builtin-shell-tool Specification

## Purpose
宿主机 Shell 命令执行工具（bash_exec），面向运维/DevOps 场景，全量审批 + 超时/取消控制，与 Docker 沙箱 run_code 互补共存。

## Requirements

### Requirement: bash_exec 在宿主机直接执行 Shell 命令
`bash_exec` SHALL 在宿主机 Shell 环境中执行任意命令，返回 stdout、stderr 和退出码。`bash_exec` 与 `run_code` 互补：`run_code` 为 Docker 隔离的 Python 沙箱（不可信代码执行），`bash_exec` 为宿主机直接执行（运维/DevOps 场景）。二者同时存在，不互相替代。

#### Scenario: 执行系统命令并返回输出
- **WHEN** 调用 `bash_exec(command="git status", description="查看 git 工作区状态")`
- **THEN** 返回命令的 stdout 输出、非零退出码（若有）和 stderr（若非空）

#### Scenario: 命令退出码非零时包含在返回值中
- **WHEN** 执行命令返回非零退出码
- **THEN** 返回结果末尾附加 `"[exit N]"` 标记，stdout/stderr 正常返回

### Requirement: bash_exec 要求提供人类可读的 description
`bash_exec` SHALL 要求 `description` 参数（字符串，5-10 词，描述命令意图），该参数为 LLM schema 中的必填项，用于 permission_gate 审批界面展示给用户。`description` 必须在命令执行前提供。

#### Scenario: 未提供 description 时拒绝执行
- **WHEN** 调用 `bash_exec` 时 `description` 为空字符串或缺失
- **THEN** 返回参数校验错误，命令不被执行

#### Scenario: description 在审批界面展示
- **WHEN** permission_gate 触发审批请求
- **THEN** 审批展示内容包含 `description` 字段（而非裸命令），帮助用户理解操作意图

### Requirement: bash_exec 通过 permission_gate 全量审批
`bash_exec` 的 `risk_level` SHALL 为 `"high"`，每次调用均 SHALL 触发 permission_gate 审批流程，用户批准后方可执行。

#### Scenario: 每次执行触发审批
- **WHEN** agent 调用 `bash_exec`
- **THEN** permission_gate 暂停执行，等待用户批准或拒绝

#### Scenario: 用户拒绝时命令不执行
- **WHEN** 用户在 permission_gate 中拒绝
- **THEN** 命令不执行，返回 `"执行已被用户拒绝"`

### Requirement: bash_exec 支持取消和超时
`bash_exec` SHALL 接受 `cancel_token`（out-of-band，opt-in）和 `timeout`（秒，默认 120.0）参数；超时时 SIGTERM → 2 秒等待 → SIGKILL 终止进程，返回超时提示；收到 cancel_token 取消信号时同样终止进程。

#### Scenario: 命令超时后终止
- **WHEN** 命令执行时间超过 `timeout` 秒
- **THEN** 进程被终止，返回 `"bash_exec 执行超时（{timeout}s），命令已终止"`

#### Scenario: 取消信号终止正在执行的命令
- **WHEN** cancel_token 被取消（用户中断）
- **THEN** 子进程被终止，返回 `"执行已取消"`

### Requirement: bash_exec 对大输出应用溢出策略
`bash_exec` 的输出 SHALL 遵循 `tool-result-truncation` 的溢出策略（50KB 阈值 + 溢出文件），`self_truncates=True` 确保不被通用截断二次处理，stdout 和 stderr 合并后统一进入溢出判断。

#### Scenario: 小输出直接返回
- **WHEN** stdout + stderr 合并后 ≤ 50KB
- **THEN** 直接返回完整输出

#### Scenario: 大输出写溢出文件
- **WHEN** stdout + stderr 合并后 > 50KB
- **THEN** 完整输出写入溢出文件，返回前 100 行 + 文件路径 + 分段读取提示

### Requirement: bash_exec 支持指定工作目录
`bash_exec` SHALL 接受可选 `workdir` 参数（字符串，默认为空），非空时作为命令的 working directory。

#### Scenario: 指定工作目录执行命令
- **WHEN** 调用 `bash_exec(command="ls", workdir="/opt/app", description="列出应用目录")`
- **THEN** 命令在 `/opt/app` 目录下执行，返回该目录内容
