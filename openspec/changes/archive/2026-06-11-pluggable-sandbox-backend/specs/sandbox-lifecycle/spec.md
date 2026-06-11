# sandbox-lifecycle（delta）

## ADDED Requirements

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

## MODIFIED Requirements

### Requirement: agent scope 闲置超时自动销毁

`agent` scope 容器闲置时间超过配置的 `idle_hours`（默认 2 小时）时，闲置回收 SHALL 销毁该容器；`session` scope 容器 MUST NOT 参与闲置回收。销毁前是否固化依赖按后端 `persist_workspace` capability 决定（支持则先固化，不支持则直接销毁并告警）。

#### Scenario: 超时容器被回收
- **WHEN** 某 `agent` scope 容器距上次使用超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被销毁（支持固化的后端先固化依赖；不支持的后端直接销毁并记录警告）

#### Scenario: 未超时容器保留
- **WHEN** 某 `agent` scope 容器距上次使用未超过 `idle_hours`，触发闲置回收
- **THEN** 该容器被保留，不受影响

## REMOVED Requirements

### Requirement: agent scope 以可写 rootfs 创建并经 docker commit 固化依赖
**Reason**: 依赖固化从「必经 docker commit」泛化为后端 capability 门控；可写 rootfs 前提与 Docker 行为完整保留在新需求中。
**Migration**: 由本 delta 的 ADDED 需求「agent scope 以可写 rootfs 创建，依赖固化按后端 capability 执行」承接。

### Requirement: 沙箱客户端支持按归属命名与依赖固化
**Reason**: 「客户端」收敛为后端抽象——按名创建/查找属核心面、固化属 capability 门控面，归属移至 `sandbox-backend-abstraction`；Docker 创建命令渲染行为已由 `sandbox-resource-limits` 既有需求覆盖。
**Migration**: 接口面见 `sandbox-backend-abstraction`「统一后端抽象接口承载沙箱执行面」；加固档/可写档渲染见 `sandbox-resource-limits`「沙箱客户端按次传入资源配置构造创建命令」。
