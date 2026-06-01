## ADDED Requirements

### Requirement: 沙箱执行受 exec_timeout 约束

`run_code` 在 Docker 容器内的代码执行 SHALL 受 `SandboxResources.exec_timeout`（秒，SB4 承载，默认 30、最长 600）约束。执行时长超过该时限时系统 MUST 判定为沙箱执行超时。本能力 SHALL 以 `exec_timeout` 形成的 deadline 与外部 cancel token 经 `parent` 链接合并为单一 token（`is_cancelled()` 同时反映沙箱 deadline 与外部取消），由该单一 token 的判定驱动中止；MUST NOT 在轮询中手写并行的 OR 合并。本能力 MUST 消费已随资源传入的 `exec_timeout`，MUST NOT 重新加载或重新校验该值（范围 clamp `[1, 600]` 由 SB4 负责）。

#### Scenario: 执行未超时正常返回
- **WHEN** 容器内代码在 `exec_timeout` 之内完成
- **THEN** 正常返回执行结果（stdout / stderr / exit_code），不触发任何强制终止

#### Scenario: 执行超过 exec_timeout 判定为超时
- **WHEN** 容器内代码执行时长超过配置的 `exec_timeout`
- **THEN** 系统判定为沙箱执行超时，进入容器侧强制终止路径

#### Scenario: 仅消费不重新校验
- **WHEN** 资源配置以 `exec_timeout`（已由 SB4 clamp 到 `[1, 600]`）传入沙箱执行路径
- **THEN** 该值被直接用作执行时限，本能力不再读取配置文件、不再做范围 clamp

### Requirement: 超时后对容器执行 docker kill 序列强制终止

沙箱执行超时（或外部取消）触发后系统 MUST 对容器执行 `docker kill` **序列**强制终止容器内进程：先发 SIGTERM，等待固定宽限期后发 SIGKILL（宽限期内 MUST NOT 轮询探测容器运行态，等满固定宽限后无条件发 SIGKILL；对已停容器再 SIGKILL 幂等无害）。宽限期 SHALL 为可注入的常量（默认 5 秒）。强制终止 MUST NOT 直接以单步 `docker rm -f` 跳过 SIGTERM 优雅窗口。

#### Scenario: 先发 SIGTERM
- **WHEN** 沙箱执行超时触发强制终止
- **THEN** 首先对容器发送 SIGTERM（`docker kill --signal=SIGTERM`），给容器内进程优雅退出窗口

#### Scenario: 宽限期后发 SIGKILL
- **WHEN** SIGTERM 后等满固定宽限期
- **THEN** 无条件对容器发送 SIGKILL（`docker kill --signal=SIGKILL`）强制杀死，期间不轮询探测容器运行态

#### Scenario: 宽限期可注入便于测试
- **WHEN** 测试将宽限期常量注入为极短值（如 0.01 秒）
- **THEN** SIGTERM 与 SIGKILL 之间的等待相应缩短，不依赖墙钟长等待

### Requirement: 沙箱执行超时归一为 sandbox_timeout 错误

沙箱执行超时 SHALL 归类为 `ErrorCategory.sandbox_timeout`（AR5 已预留的分类码），复用 `CLASSIFICATION_TABLE` 中该条目的标志位（不自动重试 / 不压缩 / 不切模型）。本能力 MUST NOT 新建独立的超时分类码，MUST NOT 修改该条目的标志位语义。返回给用户的文本 MUST 明确指出是「沙箱执行超时」，使其区别于工具崩溃与外部取消。超时 MUST 作为错误返回（不抛异常杀主循环），对话可继续。

#### Scenario: 超时归类为 sandbox_timeout
- **WHEN** 容器内代码执行超时被强制终止
- **THEN** 该错误归类为 `sandbox_timeout`，采用其既有标志位（三标志均为否）

#### Scenario: 超时作为错误返回且对话可继续
- **WHEN** 沙箱执行超时
- **THEN** 用户收到明确的「沙箱执行超时」提示，`run_code` 正常返回该错误文本而非抛出异常，对话可继续进行

#### Scenario: sandbox_timeout 预留码经沙箱执行源首次可达
- **WHEN** 沙箱执行超时发生
- **THEN** `sandbox_timeout` 作为已接入的错误源被返回，不再是「不被主动返回的预留码」

### Requirement: 区分沙箱超时与外部取消

中止路径 SHALL 区分「沙箱 `exec_timeout` 超时」与「外部 cancel token 显式取消 / 上层 deadline 到点」。两条路径都 MUST 对容器执行 `docker kill` 序列终止容器内进程，但归类与返回文本 MUST 不同：沙箱超时归 `sandbox_timeout`、文本「沙箱执行超时」；外部取消沿用既有「已取消」语义、MUST NOT 归为 `sandbox_timeout`。沙箱 deadline 与外部 token 经 `parent` 链接合并为单一 token；该 token 触发后系统 SHALL 依据子 token 自身 deadline 是否已过区分原因——deadline 已过判为沙箱执行超时，否则（父 / 外部触发）判为外部取消（与子 agent 生命周期的 `timed_out` vs `cancelled` 判定一致）。

#### Scenario: 外部 token 先到点为取消
- **WHEN** 外部 cancel token 在 `exec_timeout` deadline 之前被取消（或其上层 deadline 先到），经 `parent` 链接使合并后的单一 token 触发，且此时子 token 自身 deadline 尚未过
- **THEN** 该中止归为外部取消，返回既有「已取消」语义，不归为 `sandbox_timeout`

#### Scenario: 沙箱 deadline 先到点为超时
- **WHEN** 沙箱 `exec_timeout` 形成的 deadline 在外部 token 取消之前到点，使合并后的单一 token 触发，且此时子 token 自身 deadline 已过
- **THEN** 该中止归为沙箱执行超时，归类 `sandbox_timeout`、文本「沙箱执行超时」

### Requirement: 不越界改动工具层超时与容器去留策略

本能力 MUST NOT 实现工具层通用超时（任意工具的 await 层竞速、`tool_timeout` 归类）——该职责属兄弟能力 `tool-timeout`（T2）。本能力 MUST NOT 改变 SB2 的 scope→容器保留/销毁策略：`docker kill` 仅终止容器内进程，终止后容器的保留或销毁沿用既有约定。

> 归属说明：本需求是 Docker 后端的新增治理能力，落在本 change 的新 capability `sandbox-exec-timeout` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。

#### Scenario: 不触碰非 run_code 工具的超时
- **WHEN** 一个非 `run_code` 工具（IO / MCP / 外部进程）执行
- **THEN** 本能力不对其施加 `exec_timeout`，也不对其调用 `docker kill`（其超时由 `tool-timeout` 在工具层处理）

#### Scenario: 终止后容器去留沿用 SB2 约定
- **WHEN** 沙箱执行超时对容器执行 `docker kill` 后
- **THEN** 容器的保留（供同 session / 同 agent 复用）或销毁沿用 SB2 既有 scope 策略，本能力不另行改动该策略
