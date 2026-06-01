# sandbox-orphan-cleanup Specification

## Purpose
TBD - created by archiving change sandbox-orphan-cleanup. Update Purpose after archive.
## Requirements
### Requirement: 清理 sandbox 前缀的孤儿容器

孤儿清理 SHALL 枚举所有以 `sandbox-` 前缀命名的容器并逐个销毁，回收上次异常退出遗留的资源，返回成功销毁的数量。清理 MUST NOT 销毁名称不以 `sandbox-` 开头的容器。

#### Scenario: 销毁遗留的沙箱容器
- **WHEN** 存在若干 `sandbox-` 前缀的遗留容器，触发清理
- **THEN** 这些容器被销毁，返回的计数等于被销毁的数量

#### Scenario: 不误删非沙箱容器
- **WHEN** 容器列表中混有名称不以 `sandbox-` 开头的容器
- **THEN** 这些容器不被销毁

#### Scenario: 无遗留容器时计数为零
- **WHEN** 没有任何 `sandbox-` 前缀容器，触发清理
- **THEN** 返回计数为 0，不执行任何销毁

### Requirement: 平台启动时自动清理且不阻断启动

平台启动时 SHALL 自动触发一次孤儿清理。清理过程中发生错误（含 Docker 不可用）时 MUST 记录警告，平台 MUST 正常完成启动，不被清理失败阻断。

> 前提：本需求假设**单个平台实例独占一个 Docker daemon**（沙箱轨整体前提）。基于此，启动期本进程尚未创建任何 `sandbox-*` 容器，则当前所有 `sandbox-*` 容器必为本实例上次遗留的孤儿，启动期全删安全。多实例共享同一 Docker 宿主（HA）不在支持范围——该拓扑下全删会误删同伴实例的活跃容器、且 `sandbox-agent-{name}` 跨实例撞名，列为未来工作（见 design 部署前提）。

> 探测协调：启动期 Docker 可用性探测与 SB3 合并为**一次探测**，结果同时驱动 SB3 mode 降级与本需求是否执行清理（可用才清理）。

#### Scenario: 启动时触发清理
- **WHEN** 平台启动且 Docker 可用
- **THEN** 孤儿清理被调用一次

#### Scenario: 清理失败不阻断启动
- **WHEN** 启动时清理抛出错误或 Docker 不可用
- **THEN** 记录警告，平台仍正常完成启动

#### Scenario: 清理记录被删容器供审计
- **WHEN** 清理销毁了若干 `sandbox-` 前缀容器
- **THEN** 记录清理计数与被删容器名列表（供运维审计）

### Requirement: 提供不依赖调度器的按需触发入口

孤儿清理 SHALL 提供可被手动调用的独立入口，调用方式 MUST NOT 依赖任何定时调度器。

#### Scenario: 手动触发清理
- **WHEN** 运维或管理工具手动调用清理入口
- **THEN** 执行一次清理并返回销毁计数，无需任何调度器参与

#### Scenario: Docker 不可用时安全跳过
- **WHEN** 触发清理但 Docker 不可用
- **THEN** 清理返回计数 0、不抛异常

### Requirement: 沙箱客户端支持按前缀枚举容器

沙箱客户端 SHALL 支持按名称前缀枚举容器，返回名称列表供清理使用。Docker 不可用或枚举命令失败时 MUST 返回空列表且不抛异常。既有创建、执行、销毁能力的可观察行为不变。

> 归属说明：本需求是 Docker 后端新增能力，落在本 change 的新 capability `sandbox-orphan-cleanup` 下以 ADDED 表达。既有 `openspec/specs/sandbox-client/spec.md` 主 spec 仍为 microsandbox 历史版本，属既有技术债，不在本 change 范围。

#### Scenario: 枚举匹配前缀的容器
- **WHEN** 按 `sandbox-` 前缀枚举
- **THEN** 返回所有匹配该前缀的容器名称列表

#### Scenario: 枚举失败安全返回
- **WHEN** Docker 不可用或枚举命令返回非零
- **THEN** 返回空列表，不抛异常

