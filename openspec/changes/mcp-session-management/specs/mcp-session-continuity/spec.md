## ADDED Requirements

### Requirement: 会话过期透明重建并重试

当 `transport: http` 服务的 `tools/list` 或 `tools/call` 请求收到服务端会话失效响应（HTTP 404，或 4xx 且响应明确指示 `Mcp-Session-Id` 失效）时，平台 SHALL 清空该服务本地保存的会话标识、重新发起 `initialize` 取得新会话标识，并以新标识对原请求重试。重建成功时调用方 MUST 无感知地拿到正常结果。

#### Scenario: 会话过期后透明重建并取得结果
- **WHEN** 某 `http` 服务的 `tools/call` 请求因会话过期收到 HTTP 404
- **THEN** 平台清空旧会话标识、重新 `initialize` 取得新会话标识、以新标识重试该工具调用，调用方拿到与会话有效时一致的工具结果

#### Scenario: 注册期会话过期同样重建
- **WHEN** 某 `http` 服务在 `tools/list`（注册阶段）因会话过期收到 HTTP 404
- **THEN** 平台重新 `initialize` 后重试列举，服务工具仍以 `{server_id}__{tool_name}` 命名空间正常注册

### Requirement: 会话重建至多一次

会话过期触发的透明重建 SHALL 对同一请求至多发生一次。该「至多一次」守卫与请求路径无关：无论会话失效发生在 `tools/call`（调用期）还是 `tools/list`（注册期），守卫都作用于二者共享的请求层（`_post_jsonrpc`）。若重建并重试后仍返回会话失效或失败，平台 MUST NOT 继续重建，而是按既有错误路径上抛，交由降级/上层处理。

#### Scenario: 连续过期不无限重建
- **WHEN** 某请求重建会话并重试后，重试响应仍为会话失效（HTTP 404）
- **THEN** 平台不再发起第二次重建，直接将该错误上抛

#### Scenario: 注册期连续过期同样不无限重建
- **WHEN** 某 `http` 服务在 `tools/list`（注册阶段）重建会话并重试后，重试响应仍为会话失效（HTTP 404）
- **THEN** 平台不再发起第二次重建，直接将该错误上抛（与调用期对称，守卫在共享请求层）

### Requirement: 认证失败不触发会话重建

收到认证失败响应（HTTP 401/403）时，平台 MUST NOT 将其判定为会话过期，MUST NOT 清空会话标识或重新 `initialize`，而是按错误路径上抛。会话重建仅针对会话失效语义，不掩盖认证问题。

#### Scenario: 401 不触发会话重建
- **WHEN** 某 `http` 服务的工具调用收到 HTTP 401
- **THEN** 平台不清空该服务会话标识、不重新 `initialize`，直接上抛该错误

### Requirement: 会话生命周期按服务隔离持有

会话标识的开启、复用、过期与关闭 SHALL 按服务实例隔离持有，MUST NOT 置于模块级可变全局状态。后续对同一服务的请求复用其会话标识；过期时清空该服务标识；不同服务的会话标识互不影响。

#### Scenario: 会话标识随服务实例持有
- **WHEN** `initialize` 响应为某服务分配会话标识
- **THEN** 该标识保存在该服务实例上，后续同服务请求回携，且不影响其他服务的会话标识

### Requirement: 关停时主动释放会话

平台关停时 SHALL 对每个持有会话标识的 `http` 服务向其会话端点发送 HTTP `DELETE`（携带 `Mcp-Session-Id` 头）以通知服务端释放会话，随后清空本地会话标识。该释放为 best-effort：`DELETE` 失败 MUST 仅记录日志，不得抛出或阻断关停。

#### Scenario: 关停时对活跃会话发 DELETE
- **WHEN** 平台关停且某 `http` 服务持有会话标识
- **THEN** 平台向该服务会话端点发送携带 `Mcp-Session-Id` 的 `DELETE`，并清空本地会话标识

#### Scenario: 无会话标识时不发 DELETE
- **WHEN** 平台关停且某 `http` 服务未持有会话标识
- **THEN** 平台不对该服务发送 `DELETE`

#### Scenario: DELETE 失败不阻断关停
- **WHEN** 关停时对某活跃会话发送的 `DELETE` 失败（服务端不可达或不支持）
- **THEN** 平台仅记录日志，关停流程继续完成，不抛出异常
