# sandbox-orphan-cleanup（delta）

## ADDED Requirements

### Requirement: 沙箱后端按前缀枚举工作区为 capability 门控能力

按名称前缀枚举遗留工作区 SHALL 是 `orphan_cleanup` capability 门控的后端能力：声明支持的后端（Docker）MUST 实现 `list_workspaces(prefix)` 返回名称列表，后端不可用或枚举失败时 MUST 返回空列表且不抛异常；未声明支持的后端上，孤儿清理 MUST 静默跳过并记录一条说明日志，MUST NOT 调用枚举方法。既有创建、执行、销毁能力的可观察行为不变。

#### Scenario: 枚举匹配前缀的容器
- **WHEN** Docker 后端下按 `sandbox-` 前缀枚举
- **THEN** 返回所有匹配该前缀的容器名称列表

#### Scenario: 枚举失败安全返回
- **WHEN** Docker 后端下 Docker 不可用或枚举命令返回非零
- **THEN** 返回空列表，不抛异常

#### Scenario: 不支持枚举的后端清理跳过
- **WHEN** 选定后端未声明 `orphan_cleanup`，孤儿清理被触发
- **THEN** 清理静默跳过（返回计数 0）、记录一条说明日志，不调用后端枚举方法、不抛异常

## MODIFIED Requirements

### Requirement: 平台启动时自动清理且不阻断启动

平台启动时 SHALL 自动触发一次孤儿清理。清理过程中发生错误（含选定后端不可用）时 MUST 记录警告，平台 MUST 正常完成启动，不被清理失败阻断。选定后端未声明 `orphan_cleanup` capability 时，启动清理 SHALL 静默跳过并记录说明。

> 前提：本需求假设**单个平台实例独占一个沙箱后端**（沙箱轨整体前提）。基于此，启动期本进程尚未创建任何 `sandbox-*` 工作区，则当前所有 `sandbox-*` 工作区必为本实例上次遗留的孤儿，启动期全删安全。多实例共享同一后端宿主（HA）不在支持范围——该拓扑下全删会误删同伴实例的活跃工作区、且 `sandbox-agent-{name}` 跨实例撞名，列为未来工作（见 design 部署前提）。

> 探测协调：启动期后端可用性探测与 SB3 合并为**一次探测**，结果同时驱动 SB3 mode 降级与本需求是否执行清理（可用且支持枚举才清理）。

#### Scenario: 启动时触发清理
- **WHEN** 平台启动且选定后端可用并声明 `orphan_cleanup`
- **THEN** 孤儿清理被调用一次

#### Scenario: 清理失败不阻断启动
- **WHEN** 启动时清理抛出错误或选定后端不可用
- **THEN** 记录警告，平台仍正常完成启动

#### Scenario: 清理记录被删容器供审计
- **WHEN** 清理销毁了若干 `sandbox-` 前缀工作区
- **THEN** 记录清理计数与被删工作区名列表（供运维审计）

### Requirement: 提供不依赖调度器的按需触发入口

孤儿清理 SHALL 提供可被手动调用的独立入口，调用方式 MUST NOT 依赖任何定时调度器。

#### Scenario: 手动触发清理
- **WHEN** 运维或管理工具手动调用清理入口
- **THEN** 执行一次清理并返回销毁计数，无需任何调度器参与

#### Scenario: 后端不可用或不支持枚举时安全跳过
- **WHEN** 触发清理但选定后端不可用，或其未声明 `orphan_cleanup`
- **THEN** 清理返回计数 0、不抛异常

## REMOVED Requirements

### Requirement: 沙箱客户端支持按前缀枚举容器
**Reason**: 枚举从客户端 Docker 专属方法泛化为 `orphan_cleanup` capability 门控的后端能力。
**Migration**: 由本 delta 的 ADDED 需求「沙箱后端按前缀枚举工作区为 capability 门控能力」承接；Docker 后端实现细节（`docker ps -a --filter`、失败返空）不变。
