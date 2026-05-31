## ADDED Requirements

### Requirement: 沙箱容器按 scope 决定存活粒度

沙箱生命周期层 SHALL 支持两种存活粒度（scope）：`session`（默认）与 `agent`。`session` scope 的容器以会话为归属边界，`agent` scope 的容器以 agent 定义为归属边界。每个容器 MUST 有唯一且编码了归属信息的名称，scope 与归属 key 不同的请求 MUST 取得相互隔离的容器。

#### Scenario: session scope 默认生效
- **WHEN** 配置未显式指定 scope，沙箱生命周期层为某会话取得容器
- **THEN** 该容器以 `session` scope 创建，名称编码了该会话的归属信息

#### Scenario: 不同归属取得隔离容器
- **WHEN** 两个不同 session（或两个不同 agent）分别取得沙箱容器
- **THEN** 两者得到名称不同、相互隔离的容器，一方在容器内产生的状态对另一方不可见

### Requirement: session scope 会话内复用、会话结束销毁

在 `session` scope 下，同一会话内多次请求沙箱执行 SHALL 复用同一容器（已存在则不新建）；会话结束时该容器 MUST 被销毁。

#### Scenario: 同一会话内复用容器
- **WHEN** 同一会话内第二次请求沙箱执行
- **THEN** 复用首次创建的同一容器，不新建容器

#### Scenario: 会话结束销毁容器
- **WHEN** 会话结束并触发释放
- **THEN** 该会话的 `session` scope 容器被销毁并从登记中移除，不影响其它会话的容器

### Requirement: agent scope 以可写 rootfs 创建并经 docker commit 固化依赖

在 `agent` scope 下，同一 agent 在不同会话中请求沙箱执行 SHALL 复用该 agent 独享的容器。agent scope 容器 MUST 以**可写 rootfs** 创建（不施加 `--read-only`，`read_only=False`），使安装的依赖落地于 rootfs；容器在销毁前 MUST 通过 `docker commit` 将该可写 rootfs 上的已装依赖固化为镜像层，下次为同一 agent 新建容器时 SHALL 以该镜像为基础镜像恢复，无需重装依赖。作为对比，`session` scope 容器 MUST 以只读 rootfs（`--read-only`）+ `network=none` 全加固创建，不参与依赖固化。

> 设计依据：`--read-only` 下 site-packages 无法写入 rootfs，`docker commit` 将捕获不到依赖层；故可写 rootfs 是 agent scope 依赖固化能成立的前提。session scope 为一次性、不可信代码执行，维持最严加固。

#### Scenario: agent 容器跨会话复用
- **WHEN** 同一 agent 在新会话中再次请求沙箱执行，且其容器仍存在
- **THEN** 复用该 agent 既有容器，先前安装的依赖仍可用

#### Scenario: agent 容器以可写 rootfs 创建、session 容器只读
- **WHEN** 分别为 `agent` scope 与 `session` scope 创建容器
- **THEN** agent 容器以可写 rootfs（`read_only=False`、不带 `--read-only`、network 按配置）创建；session 容器以只读 rootfs（`--read-only`）+ `--network none` 全加固创建

#### Scenario: 销毁前固化依赖并在重建时恢复
- **WHEN** 某 agent 容器因闲置被回收
- **THEN** 回收前先 `docker commit` 把可写 rootfs 上的已装依赖固化为该 agent 的镜像层，下次为同一 agent 新建容器时以该镜像为基础镜像

### Requirement: agent scope 闲置超时自动销毁

`agent` scope 容器闲置时间超过配置的 `idle_hours`（默认 2 小时）时，闲置回收 SHALL 销毁该容器；`session` scope 容器 MUST NOT 参与闲置回收。

#### Scenario: 超时容器被回收
- **WHEN** 某 `agent` scope 容器距上次使用超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被销毁（销毁前先固化依赖）

#### Scenario: 未超时容器保留
- **WHEN** 某 `agent` scope 容器距上次使用未超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被保留，不受影响

### Requirement: 沙箱客户端支持按归属命名与依赖固化

沙箱客户端 SHALL 支持以指定名称、指定资源档位（消费 SB4 的 `SandboxResources`）、指定基础镜像创建容器，按名称查找已存在容器，以及将运行中容器固化为镜像，供生命周期层实现复用与依赖固化。创建签名收敛为 `create_workspace(name, resources, image)`——`resources` 承载 `read_only` / `network` 等加固旗标，`image` 为基础镜像（agent scope 复用 commit 镜像即把其 tag 当 `image` 传入，不单列 `base_image`）。以加固档（`read_only=True` + `network=none`）+ 默认镜像创建时，其可观察行为 MUST 与现状一致。

> 归属说明：本需求是 Docker 后端新增能力，落在本 change 的新 capability `sandbox-lifecycle` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本（需求名为 Per-session workspace lifecycle / Tool execution in sandbox 等），属既有技术债，不在本 change 范围。

#### Scenario: 按名称查找已存在容器
- **WHEN** 以某容器名查找
- **THEN** 该名称对应容器存在时返回其标识，不存在时返回空结果，均不抛异常

#### Scenario: 固化容器为镜像
- **WHEN** 对运行中容器请求固化
- **THEN** 该容器被 `docker commit` 为指定镜像标签

#### Scenario: 加固档 + 默认镜像创建行为不变
- **WHEN** 以加固档 `resources`（`read_only=True` + `network=none`）+ 默认镜像创建容器
- **THEN** 创建命令与隔离行为与现状一致（既有调用与既有测试不受影响）

#### Scenario: 可写 rootfs 档位渲染创建命令
- **WHEN** 以 `read_only=False` 的 `resources` 创建容器
- **THEN** 创建命令不带 `--read-only`，network 按 `resources` 指定渲染
