## MODIFIED Requirements

### Requirement: 调用失败时懒重连重试一次

当持有 SDK `ClientSession` 的 MCP 服务在 `tools/call` 或 `tools/list` 因会话/连接级失效(SDK 抛出连接错误或会话失效)时,平台 SHALL 就地重开该服务的 `ClientSession`(重新经对应 SDK transport 建立 + `initialize`)并对原请求重试一次。重建成功时调用方 MUST 无感知地拿到正常结果。该懒重连取代旧的"手写 404/marker 检测 + 重新 initialize"机制。

#### Scenario: 会话失效后懒重连并取得结果
- **WHEN** 某 `http` 服务的 `tools/call` 因会话/连接失效抛错
- **THEN** 平台就地重开该服务 `ClientSession`、以新会话重试该调用,调用方拿到与会话有效时一致的工具结果

#### Scenario: 注册期失效同样懒重连
- **WHEN** 某服务在 `tools/list`(注册阶段)因会话/连接失效抛错
- **THEN** 平台重开 `ClientSession` 后重试列举,工具仍以 `{server_id}__{tool_name}` 命名空间正常注册

### Requirement: 懒重连至多一次,仍失败则降级

懒重连 SHALL 对同一请求至多发生一次。重开并重试后若仍失败,平台 MUST NOT 继续重连,而是将该服务标记为不可用并返回降级结果(「服务暂时不可用」),不崩溃 agent loop。

#### Scenario: 连续失败不无限重连
- **WHEN** 某请求懒重连并重试后仍失败
- **THEN** 平台不再发起第二次重连,将该服务标记不可用并返回降级结果

### Requirement: 会话生命周期随 SDK ClientSession 按服务隔离持有

每个服务的 `ClientSession`(及其底层传输连接)SHALL 按服务实例隔离持有,存于 `_active_sessions[(scope, server_id)]`,生命周期挂在统一的 `AsyncExitStack`。MUST NOT 置于裸模块级可变全局状态之外的位置。后续对同一服务的调用复用其 `ClientSession`;不同服务互不影响。

#### Scenario: 会话随服务实例持有
- **WHEN** 某服务注册成功
- **THEN** 其 `ClientSession` 存于 `_active_sessions[(scope, id)]`,后续同服务调用复用,且不影响其他服务

### Requirement: 关停时经 AsyncExitStack 释放会话

平台关停时 SHALL 通过关闭统一的 `AsyncExitStack` 释放所有服务的 `ClientSession` 与底层传输(由 SDK 负责其会话端点的 `DELETE` / 连接关闭,如 `terminate_on_close`)。该释放为 best-effort:单个会话关闭失败 MUST 仅记录日志,不得抛出或阻断关停。

#### Scenario: 关停释放所有会话
- **WHEN** 平台关停
- **THEN** 关闭 `AsyncExitStack`,所有持有的 `ClientSession` 经 SDK 释放,失败仅记日志不阻断

## REMOVED Requirements

### Requirement: 认证失败不触发会话重建

**Reason**: 旧机制按 HTTP 状态码(404 vs 401/403)区分"会话过期"与"认证失败"以决定是否重建;迁移后会话/连接错误由 SDK 抛出,懒重连仅在连接级错误触发,认证失败由 SDK 作为调用错误上抛、不进入重连路径。
**Migration**: 认证失败仍按错误路径返回(不被误判为会话过期),语义保留,但不再依赖平台手写的状态码分支。
