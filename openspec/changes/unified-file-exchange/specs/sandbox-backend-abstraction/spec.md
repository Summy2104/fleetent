# sandbox-backend-abstraction Delta

## MODIFIED Requirements

### Requirement: 后端声明 capability 且决策点按 capability 分支

每个后端 SHALL 声明一组 capability（`persist_workspace` 依赖固化、`workspace_mount` 宿主目录挂载、`orphan_cleanup` 按前缀枚举、`exchange_mount` 会话归属视图只读挂载）。生命周期、清理、挂载等决策点 MUST 按所声明 capability 分支决定行为，MUST NOT 以后端具体类型（isinstance 或等价判断）分支。Docker 后端四项 capability 均 MUST 为真（既有三项行为与现状一致，`exchange_mount` 为本变更新增）。

#### Scenario: Docker 后端全量 capability

- **WHEN** 选定 Docker 后端
- **THEN** 依赖固化、宿主挂载、按前缀枚举行为与引入抽象前完全一致，且容器创建携带 exchange 归属视图只读挂载

#### Scenario: 决策点不感知后端类型

- **WHEN** 新增一个声明了 capability 的后端
- **THEN** 生命周期/清理/挂载决策点无需修改即按其 capability 取得正确行为

#### Scenario: 无 exchange_mount 的后端走降级

- **WHEN** 选定后端未声明 `exchange_mount`
- **THEN** 容器创建不携带视图挂载，`/exchange` 消费按 sandbox-workspace-mount 的 staging 降级条款执行
