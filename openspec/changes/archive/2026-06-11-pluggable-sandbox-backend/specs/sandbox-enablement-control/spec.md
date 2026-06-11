# sandbox-enablement-control（delta）

## ADDED Requirements

### Requirement: 选定后端不可用时自动降级为 off

平台启动时 SHALL 经选定后端的 `available()` 探测其可用性。后端不可用（Docker CLI 缺失/失败，或 msb server 不可达/认证失败）时，生效 mode MUST 降级为 `off`、记录警告，且平台 MUST 正常启动不被阻断。

#### Scenario: Docker 后端不可用降级且不阻断启动
- **WHEN** 选定 Docker 后端且启动时 Docker CLI 不可用
- **THEN** 生效 mode 为 `off`、`run_code` 不注册、记录一条警告，平台正常完成启动

#### Scenario: microsandbox 后端不可用同样降级
- **WHEN** 选定 microsandbox 后端且启动时 msb server 不可达
- **THEN** 生效 mode 为 `off`、记录一条警告，平台正常完成启动

#### Scenario: 探测失败不抛异常
- **WHEN** 任一后端的可用性探测命令报错或依赖缺失
- **THEN** 探测返回不可用且不抛异常，由降级逻辑接管

### Requirement: 沙箱后端提供可用性探测

每个沙箱后端 SHALL 实现可用性探测 `available()`，返回布尔结果供启用控制层判定降级。探测在后端依赖未安装、服务不可达或探测命令失败时 MUST 返回不可用且不抛异常。既有创建、执行、销毁能力的可观察行为保持不变。

#### Scenario: 探测可用
- **WHEN** 选定后端的底层服务可正常响应探测
- **THEN** `available()` 返回可用

#### Scenario: 探测不可用安全返回
- **WHEN** 选定后端的底层服务不存在或探测失败
- **THEN** `available()` 返回不可用，不抛异常

## REMOVED Requirements

### Requirement: Docker 不可用时自动降级为 off
**Reason**: 降级判据从「Docker 可用性」泛化为「选定后端可用性」，Docker 行为作为其中一种后端完整保留。
**Migration**: 由本 delta 的 ADDED 需求「选定后端不可用时自动降级为 off」承接。

### Requirement: 沙箱客户端提供 Docker 可用性探测
**Reason**: 探测从客户端的 Docker 专属方法（`docker_available`）泛化为后端接口方法（`available()`）。
**Migration**: 由本 delta 的 ADDED 需求「沙箱后端提供可用性探测」承接；Docker 后端的探测实现细节（`docker version` 轻探测）不变。
