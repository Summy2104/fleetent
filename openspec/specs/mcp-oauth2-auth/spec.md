# mcp-oauth2-auth Specification

## Purpose
TBD - created by archiving change mcp-oauth2. Update Purpose after archive.
## Requirements
### Requirement: OAuth2 客户端认证向自托管 token 端点取 token

平台 SHALL 支持 `auth_type: "oauth2"` 的 MCP 服务：按 OAuth2 标准（首选 client_credentials 授权类型）向该服务配置的 token 端点请求 access token。token 端点 MUST 为客户可自托管的授权服务器地址，平台仅作为 OAuth2 客户端，MUST NOT 依赖任何云托管专有身份服务；因 SDK 不提供 client_credentials 授权类型，向 token 端点取 token 的请求由平台自身发起（非经 SDK 的 OAuthClientProvider）。

取得的 access token MUST 经 SDK 传输层的 `auth=`（一个 `httpx.Auth`）**按请求注入** `Authorization: Bearer <access_token>`，而非在建立会话时一次性解析进会话的静态请求头。注入 MUST 对所有经该传输的请求生效（含 initialize 握手与各工具调用），且持久会话存续期间每次请求都重新取用当前有效 token。

#### Scenario: oauth2 服务取 token 并经 auth= 按请求注入 Bearer
- **WHEN** 一个 `auth_type: "oauth2"` 的服务发起请求且已配置 token 端点与凭据
- **THEN** 平台向 token 端点取得 access token，并经 SDK 传输层 `auth=` 在该请求头按请求注入 `Authorization: Bearer <access_token>`

#### Scenario: 持久会话内每请求取用当前 token（非建会话时一次性烘焙）
- **WHEN** 一个 `oauth2` 服务的持久会话已建立，随后对其发起多次工具调用
- **THEN** 每次请求都经 `auth=` 重新取用当前有效 token 注入，而非复用建立会话时烘焙进静态请求头的旧 token

#### Scenario: 非 oauth2 服务认证行为不变
- **WHEN** 一个 `auth_type: "api_key"` 或 `"none"` 的服务发起请求
- **THEN** 其认证行为与现状一致（api_key 的静态 Bearer 仍经请求头注入），不受 OAuth2 注入路径改造影响

### Requirement: access token 过期前自动刷新且对调用透明

平台 SHALL 依据 token 的过期时间在临近或已过期时自动刷新 access token。刷新主路径 SHALL 为按 client_credentials 重新获取（client_credentials 响应通常不含 refresh token）；仅当服务端非标准地返回了 refresh token 时 MAY 优先使用之。平台 MUST NOT 因响应不含 refresh token 而判定刷新失败。刷新成功时对工具调用 MUST 透明（调用方无感知）。平台 MUST NOT 使用已过期的 access token 发起请求。

由于会话经 SDK 持久保持，token 刷新 MUST 在**不重建会话**的前提下于按请求注入路径内完成：当某请求因 token 失效收到 token 端点/资源端的 `401` 时，平台 SHALL 在该注入路径内清除缓存 token、刷新取得新 token 并对该请求重试一次；重试成功对调用方透明。平台 MUST NOT 依赖连接级断线重连来刷新 token（`401` 不属断线）。

#### Scenario: token 过期时自动刷新并透明完成调用
- **WHEN** 某 `oauth2` 服务的 access token 已过期，此时发起工具调用
- **THEN** 平台先刷新取得新 token 再发起请求，调用方拿到正常工具结果，无需感知刷新发生

#### Scenario: 持久会话内请求收到 401 时刷新并重试一次
- **WHEN** 某 `oauth2` 服务的持久会话存续期间，某请求因 token 失效收到 `401`
- **THEN** 平台在按请求注入路径内清除缓存 token、刷新取新 token 并对该请求重试一次，调用方拿到正常结果，且无需重建会话

#### Scenario: 不使用过期 token 发起请求
- **WHEN** access token 已过期且刷新失败
- **THEN** 平台不使用过期 token 发起请求，转入认证失败处理

### Requirement: token 存储按服务隔离且可注入

access token 及其过期时间（与可选 refresh token）的存储 SHALL 按服务实例隔离持有，MUST NOT 置于模块级可变全局状态。存储后端 MUST 可注入以便隔离测试（默认内存；若持久化则其存储路径 MUST 可在测试中替换隔离）。不同服务的 token MUST 互不影响。

#### Scenario: 不同服务的 token 互不影响
- **WHEN** 两个 `oauth2` 服务各自取得 access token
- **THEN** 各服务的 token 按其自身实例隔离保存，互不覆盖、互不影响

### Requirement: 认证失败标记服务认证不可用并提示重新授权

当 token 获取或刷新返回**真认证错误**（如 token 端点 401 / `invalid_client` / `invalid_grant`）时，平台 SHALL 将该服务标记为**认证不可用**并给出需重新授权或检查 OAuth2 凭据的提示。平台 MUST NOT 在凭据错误下反复无效地重试 token 端点。token 端点返回的 **5xx / 网络错误 / 超时** 属瞬时错误，平台 MUST NOT 据此将服务标记为认证不可用，而 MUST 按可重试处理。服务处于认证不可用状态期间，对其工具的调用 MUST 直接返回明确的「认证不可用」结果（不取 token、不发起请求、不抛异常、不卡住），且 MUST NOT 影响其他服务。该「认证不可用」是独立于连接级健康状态的正交标志：MUST NOT 依赖连接级健康/重连能力（MCP3）才能生效。该认证不可用标志的恢复触发点为配置重载 / 重新注册（清除标志后下次调用重新取 token），平台 MUST NOT 依赖定时退避重试来自动清除该标志；凭据或配置更新后，平台 SHALL 能恢复对该服务的认证。

#### Scenario: 认证失败标记不可用并提示
- **WHEN** 某 `oauth2` 服务的 token 获取因 `invalid_client` 失败
- **THEN** 平台将该服务标记为认证不可用，给出需重新授权 / 检查凭据的提示，且不反复重试 token 端点

#### Scenario: token 端点瞬时错误不标记认证不可用且可重试
- **WHEN** 某 `oauth2` 服务取 token 时 token 端点返回 5xx 或发生网络错误 / 超时
- **THEN** 平台不将该服务标记为认证不可用，按可重试处理，下次调用可正常重试取 token

#### Scenario: 配置重载 / 重新注册清除认证不可用标志
- **WHEN** 一个被标记为认证不可用的 `oauth2` 服务发生配置重载或重新注册
- **THEN** 平台清除其「认证不可用」标志，下次调用重新取 token（不依赖定时退避自动清除）

#### Scenario: 凭据更新后恢复认证
- **WHEN** 一个认证不可用的 `oauth2` 服务在其凭据/配置更新后再次取 token 且成功
- **THEN** 平台恢复对该服务的认证，其请求重新携带有效 Bearer token

#### Scenario: 对认证不可用的 oauth2 服务发起工具调用
- **WHEN** agent 对一个已被标记为「认证不可用」的 `oauth2` 服务发起工具调用
- **THEN** 该调用不取 token、不向 token 端点或 MCP 服务发起请求，直接返回明确的「认证不可用，需重新授权 / 检查 OAuth2 凭据」结果（不抛异常、不卡住），其他服务的工具调用不受影响

