# sandbox-exec-timeout（delta）

## ADDED Requirements

### Requirement: 超时后经后端强制终止沙箱内执行

沙箱执行超时（或外部取消）触发后系统 MUST 经后端抽象的 `kill_workspace` 强制终止沙箱内进程，终止机制为各后端实现细节：

- Docker 后端 MUST 实现为 `docker kill` **序列**：先发 SIGTERM，等待固定宽限期后发 SIGKILL（宽限期内 MUST NOT 轮询探测容器运行态，等满固定宽限后无条件发 SIGKILL；对已停容器再 SIGKILL 幂等无害）。宽限期 SHALL 为可注入的常量（默认 5 秒）。MUST NOT 直接以单步 `docker rm -f` 跳过 SIGTERM 优雅窗口
- microsandbox 后端 MUST 实现为 SDK 原生 stop，不模拟信号序列

#### Scenario: Docker 后端先发 SIGTERM
- **WHEN** Docker 后端下沙箱执行超时触发强制终止
- **THEN** 首先对容器发送 SIGTERM（`docker kill --signal=SIGTERM`），给容器内进程优雅退出窗口

#### Scenario: Docker 后端宽限期后发 SIGKILL
- **WHEN** Docker 后端下 SIGTERM 后等满固定宽限期
- **THEN** 无条件对容器发送 SIGKILL 强制杀死，期间不轮询探测容器运行态

#### Scenario: 宽限期可注入便于测试
- **WHEN** 测试将宽限期常量注入为极短值（如 0.01 秒）
- **THEN** SIGTERM 与 SIGKILL 之间的等待相应缩短，不依赖墙钟长等待

#### Scenario: microsandbox 后端原生 stop
- **WHEN** microsandbox 后端下沙箱执行超时触发强制终止
- **THEN** 对该沙箱执行 SDK stop，超时归类与返回文本与 Docker 后端一致

## MODIFIED Requirements

### Requirement: 区分沙箱超时与外部取消

中止路径 SHALL 区分「沙箱 `exec_timeout` 超时」与「外部 cancel token 显式取消 / 上层 deadline 到点」。两条路径都 MUST 经后端 `kill_workspace` 终止沙箱内进程，但归类与返回文本 MUST 不同：沙箱超时归 `sandbox_timeout`、文本「沙箱执行超时」；外部取消沿用既有「已取消」语义、MUST NOT 归为 `sandbox_timeout`。沙箱 deadline 与外部 token 经 `parent` 链接合并为单一 token；该 token 触发后系统 SHALL 依据子 token 自身 deadline 是否已过区分原因——deadline 已过判为沙箱执行超时，否则（父 / 外部触发）判为外部取消（与子 agent 生命周期的 `timed_out` vs `cancelled` 判定一致）。

#### Scenario: 外部 token 先到点为取消
- **WHEN** 外部 cancel token 在 `exec_timeout` deadline 之前被取消（或其上层 deadline 先到），经 `parent` 链接使合并后的单一 token 触发，且此时子 token 自身 deadline 尚未过
- **THEN** 该中止归为外部取消，返回既有「已取消」语义，不归为 `sandbox_timeout`

#### Scenario: 沙箱 deadline 先到点为超时
- **WHEN** 沙箱 `exec_timeout` 形成的 deadline 在外部 token 取消之前到点，使合并后的单一 token 触发，且此时子 token 自身 deadline 已过
- **THEN** 该中止归为沙箱执行超时，归类 `sandbox_timeout`、文本「沙箱执行超时」

## REMOVED Requirements

### Requirement: 超时后对容器执行 docker kill 序列强制终止
**Reason**: 强制终止泛化为后端抽象的 `kill_workspace`；Docker 的信号序列（SIGTERM-宽限-SIGKILL、宽限可注入、不轮询、幂等）完整保留为 Docker 后端实现细节。
**Migration**: 由本 delta 的 ADDED 需求「超时后经后端强制终止沙箱内执行」承接。
