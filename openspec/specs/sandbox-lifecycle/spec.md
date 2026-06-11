# sandbox-lifecycle Specification

## Purpose
TBD - created by archiving change sandbox-lifecycle. Update Purpose after archive.
## Requirements

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

### Requirement: agent scope 闲置超时自动销毁

`agent` scope 容器闲置时间超过配置的 `idle_hours`（默认 2 小时）时，闲置回收 SHALL 销毁该容器；`session` scope 容器 MUST NOT 参与闲置回收。销毁前是否固化依赖按后端 `persist_workspace` capability 决定（支持则先固化，不支持则直接销毁并告警）。

#### Scenario: 超时容器被回收
- **WHEN** 某 `agent` scope 容器距上次使用超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被销毁（支持固化的后端先固化依赖；不支持的后端直接销毁并记录警告）

#### Scenario: 未超时容器保留
- **WHEN** 某 `agent` scope 容器距上次使用未超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被保留，不受影响

### Requirement: agent scope 以可写 rootfs 创建，依赖固化按后端 capability 执行

在 `agent` scope 下，同一 agent 在不同会话中请求沙箱执行 SHALL 复用该 agent 独享的工作区。agent scope 工作区 MUST 以**可写 rootfs** 创建（`read_only=False`），使安装的依赖落地；作为对比，`session` scope 工作区 MUST 以只读 rootfs + `network=none` 全加固创建，不参与依赖固化。

依赖固化按后端 capability 分支：

- 后端声明 `persist_workspace`（Docker）时，工作区在销毁前 MUST 被固化为镜像（`docker commit`），下次为同一 agent 新建工作区时 SHALL 以该镜像为基础镜像恢复，无需重装依赖——行为与引入抽象前一致
- 后端未声明 `persist_workspace`（microsandbox）时，回收 MUST 跳过固化直接销毁并记录一条警告；下次获取 MUST 从基础镜像启动（依赖需重装）。生命周期层 MUST NOT 调用该后端的固化方法，也 MUST NOT 在未固化的情况下让调用方误以为依赖已保留（警告日志即为明示）

> 设计依据：`--read-only` 下 site-packages 无法写入 rootfs，固化将捕获不到依赖层；故可写 rootfs 是依赖固化能成立的前提，该前提与后端无关、统一保留。

#### Scenario: agent 容器跨会话复用
- **WHEN** 同一 agent 在新会话中再次请求沙箱执行，且其工作区仍存在
- **THEN** 复用该 agent 既有工作区，先前安装的依赖仍可用

#### Scenario: agent 工作区可写、session 工作区只读全加固
- **WHEN** 分别为 `agent` scope 与 `session` scope 创建工作区
- **THEN** agent 工作区以可写 rootfs 创建；session 工作区以只读 rootfs + 网络关闭全加固创建

#### Scenario: 支持固化的后端销毁前固化并在重建时恢复
- **WHEN** Docker 后端下某 agent 工作区因闲置被回收
- **THEN** 回收前先固化为该 agent 的镜像层，下次为同一 agent 新建工作区时以该镜像为基础镜像

#### Scenario: 不支持固化的后端跳过固化直接销毁
- **WHEN** microsandbox 后端下某 agent 工作区因闲置被回收
- **THEN** 不调用固化、直接销毁该工作区，并记录一条「依赖未固化」警告

#### Scenario: 不支持固化的后端重建回退基础镜像
- **WHEN** microsandbox 后端下某 agent 的工作区被回收后再次获取
- **THEN** 新工作区从配置的基础镜像启动，不尝试查找固化镜像
