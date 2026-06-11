# microsandbox-backend（delta）

> 基于实测 `microsandbox==0.5.6`（Apache-2.0，本地嵌入式 microVM）的真实 API，见 DECISIONS.md D-spike-1。

## ADDED Requirements

### Requirement: 经官方 SDK 本地运行 microVM 并探测 runtime 可用性

microsandbox 后端 SHALL 经官方 `microsandbox` SDK 在本地运行 microVM（嵌入式 libkrunfw，无独立 server、无 server 连接配置、无 API key）。可用性探测 `available()` MUST 经 `is_installed()` 判定 runtime 是否就绪：runtime 未安装或宿主不支持硬件虚拟化时 MUST 返回不可用且不抛异常，交由启用控制层降级为 off。SDK MUST 延迟导入——后端未被选定时进程不加载 `microsandbox` 包。

#### Scenario: runtime 就绪探测可用
- **WHEN** microsandbox runtime 已安装且宿主支持虚拟化
- **THEN** `available()` 返回可用

#### Scenario: runtime 未就绪安全降级
- **WHEN** microsandbox runtime 未安装（`is_installed()` 为假）或宿主不支持虚拟化
- **THEN** `available()` 返回不可用、不抛异常，生效 mode 按既有降级规则转 off

#### Scenario: 未选定时零加载
- **WHEN** 部署选定 Docker 后端
- **THEN** 进程不导入 `microsandbox` 包，无该依赖的环境照常运行

### Requirement: 生命周期操作映射到 SDK 原语

microsandbox 后端 SHALL 将抽象接口映射到 SDK 原语：`create_workspace` → `Sandbox.create(name, image, cpus, memory, network, volumes)`，`exec` → `sandbox.exec("sh", ["-c", command], stdin, env, timeout)` 返回 `ExecOutput`（取 `stdout_text` / `stderr_text` / `exit_code`），`find_workspace` → `Sandbox.get(name)`，`destroy_workspace` → `Sandbox.remove(name)`，`kill_workspace` → `sandbox.stop()`。强制终止 MUST 用 SDK 原生 stop（其内建 SIGTERM→SIGKILL），MUST NOT 模拟 Docker 的 `docker kill` 信号序列。销毁/终止对不存在或已停止实例 MUST 幂等不抛。

#### Scenario: 创建映射资源配置
- **WHEN** 以 `memory=512`、`cpus=1.0` 创建工作区
- **THEN** `Sandbox.create` 以等价的内存与 CPU 限制启动 microVM

#### Scenario: exec 返回标准结果
- **WHEN** 在沙箱内执行命令
- **THEN** 返回的 `ExecResult` 的 stdout/stderr/exit_code 取自 `ExecOutput.stdout_text` / `stderr_text` / `exit_code`

#### Scenario: 强制终止用原生 stop
- **WHEN** 沙箱执行超时触发 `kill_workspace`
- **THEN** 对该沙箱执行 SDK 原生 stop，不发送任何 Docker 信号序列

#### Scenario: 重复销毁幂等
- **WHEN** 对不存在/已移除的沙箱再次调用销毁
- **THEN** 调用静默成功，不抛异常

### Requirement: host workspace 经 Volume.bind 绑定挂载

microsandbox 后端 SHALL 经 `Volume.bind(host_path, readonly=...)` 把宿主 workspace 目录绑定挂载到沙箱内 `/workspace`，使 `workspace_mount` capability 为真。`read_only` 资源字段 MUST 映射到 `Volume.bind(readonly=)`。未传 workspace 宿主路径时 MUST 不挂载。

#### Scenario: workspace 绑定挂载
- **WHEN** 以某宿主 workspace 路径创建工作区
- **THEN** 该宿主目录经 `Volume.bind` 挂载到沙箱 `/workspace`，沙箱内读写落到该宿主目录

#### Scenario: read_only 映射只读挂载
- **WHEN** 资源配置 `read_only=True`
- **THEN** workspace 以 `Volume.bind(readonly=True)` 只读挂载

### Requirement: 实例枚举经 Sandbox.list

microsandbox 后端 SHALL 经 `Sandbox.list()` 实现 `list_workspaces(prefix)`：返回名称匹配该前缀的沙箱列表，使 `orphan_cleanup` capability 为真。枚举失败或 runtime 不可用时 MUST 返回空列表且不抛异常。

#### Scenario: 按前缀枚举沙箱
- **WHEN** 按 `sandbox-` 前缀枚举
- **THEN** 返回所有名称匹配该前缀的 microVM 沙箱名称列表

#### Scenario: 枚举失败安全返回
- **WHEN** runtime 不可用或枚举失败
- **THEN** 返回空列表，不抛异常

### Requirement: 通用资源字段映射、Docker 专属字段忽略

microsandbox 后端 SHALL 映射通用资源字段（`memory` / `cpus` / `network` / `exec_timeout` / `read_only`，其中 `exec_timeout` 仅承载、终止由超时能力驱动）；`network` 的 `none` / `public_only` / `allow_all` MUST 1:1 映射到 `Network.none()` / `Network.public_only()` / `Network.allow_all()`。Docker 专属硬化字段（`pids_limit` / `tmpfs_size_mb` / `cap_drop_all` / `cap_add` / `no_new_privileges` / `init` / `run_as_user`）MUST 被忽略且不报错——microVM 边界天然提供隔离，无对应概念。

#### Scenario: 硬化字段被忽略不报错
- **WHEN** 资源配置含 `pids_limit=256`、`cap_drop_all=true` 等 Docker 专属字段
- **THEN** microVM 正常创建，这些字段不产生任何 SDK 参数也不报错

#### Scenario: network 策略 1:1 映射
- **WHEN** 资源配置 `network=none`（或 `public_only` / `allow_all`）
- **THEN** 沙箱以 `Network.none()`（或对应预设）启动

### Requirement: stdin 经 SDK 原生参数注入

microsandbox 后端的 `exec` SHALL 经 SDK `exec(..., stdin=...)` 原生参数传递 `stdin` 字节流，使文件工具的写入 payload 不受单条命令长度（ARG_MAX）限制。MUST NOT 用 base64 分块等绕过手段。

#### Scenario: 大 payload 写入完整
- **WHEN** 经 `exec(stdin=...)` 写入超过单条命令长度限制的内容
- **THEN** 容器内目标命令经 SDK 原生 stdin 收到完整字节流，内容与宿主侧一致

### Requirement: env 注入经敏感名防御过滤

microsandbox 后端在注入环境变量前 MUST 重跑敏感名过滤（`is_sensitive_name`），与 Docker 后端的纵深防御一致：即使调用方传入未过滤的映射，敏感命名变量也不得抵达沙箱。过滤后经 `exec(env=)` 注入。

#### Scenario: 敏感名不进沙箱
- **WHEN** 注入映射中混入 `AWS_SECRET_ACCESS_KEY` 等敏感命名变量
- **THEN** 该变量被过滤，沙箱内不可见；其余变量正常注入

### Requirement: config-hash 不可读时保守复用

microsandbox 无容器 label 机制，`inspect_config_hash` MUST 恒返回空值，使生命周期层走既有「hash 缺失 → 保守复用」路径。配置变更不触发自动重建为已知限制，MUST 在日志中可观察（复用时记录 debug 级说明）。

#### Scenario: 复用既有沙箱不校验配置
- **WHEN** 进程重启后按名找到存活的 microVM 沙箱
- **THEN** 直接复用该沙箱（不比对配置 hash），与 pre-label Docker 容器的复用语义一致

### Requirement: capability 声明反映真实能力

microsandbox 后端 SHALL 声明 `persist_workspace=False`（SDK 无运行实例固化为镜像的原语；`Snapshot` 语义不同，列未来工作）、`workspace_mount=True`（`Volume.bind`）、`orphan_cleanup=True`（`Sandbox.list`）。

#### Scenario: 不声明依赖固化
- **WHEN** microsandbox 后端被选定且 agent-scope 沙箱闲置回收触发
- **THEN** 按 `persist_workspace=False` 的降级条款执行（跳过固化直接销毁并告警）

#### Scenario: 声明挂载与枚举
- **WHEN** 查询 microsandbox 后端 capability
- **THEN** `workspace_mount` 与 `orphan_cleanup` 均为真，文件工具走容器执行、孤儿清理按前缀枚举生效
