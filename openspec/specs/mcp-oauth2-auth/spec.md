# mcp-oauth2-auth Specification

## Purpose
TBD - created by archiving change mcp-oauth2. Update Purpose after archive.
## Requirements
### Requirement: OAuth2 客户端认证向自托管 token 端点取 token

平台 SHALL 支持 `auth_type: "oauth2"` 的 MCP 服务：按 OAuth2 client_credentials 授权类型向该服务配置的 token 端点请求 access token。token 端点 MUST 为客户可自托管的授权服务器地址,平台仅作为 OAuth2 客户端,MUST NOT 依赖任何云托管专有身份服务。

取 token 与 Bearer 注入 SHALL 由官方 SDK 的 client_credentials provider(`ClientCredentialsOAuthProvider`,本身是 `httpx.Auth`)经 SDK 传输层的 `auth=` 执行,而非平台手写的 token POST。平台 SHALL 以显式配置的 token 端点(`token_url`)预填该 provider 的授权服务器元数据,使取 token 指向该显式端点而**不要求**服务端暴露 `.well-known` 发现;当服务端确实暴露发现元数据时,发现结果优先。注入 MUST 对所有经该传输的请求生效(含 initialize 握手与各工具调用)。

该 provider 的认证为**反应式**:当某请求未携带有效 token 而被资源端返回 `401` 时,SHALL 触发取 token 并以新 token 重试该请求;在 token 有效期内,后续请求直接主动携带缓存 token。客户端认证方式 SHALL 为 `client_secret_post`(client_id/secret 置于 token 请求体)。

#### Scenario: oauth2 服务经 SDK provider 取 token 并按请求注入 Bearer
- **WHEN** 一个 `auth_type: "oauth2"` 的服务的某请求未带有效 token 且被资源端返回 `401`
- **THEN** SDK provider 向(预填的)显式 token 端点按 client_credentials 取得 access token,并以 `Authorization: Bearer <access_token>` 重试该请求

#### Scenario: token 有效期内主动携带缓存 token
- **WHEN** 一个 `oauth2` 服务已取得未过期的 access token,随后发起后续工具调用
- **THEN** 后续请求直接主动携带该缓存 token,无需再次触发 401 取 token

#### Scenario: 显式 token_url 优先于发现(无需服务端 .well-known)
- **WHEN** 一个 `oauth2` 服务配置了显式 `token_url` 且其服务端未暴露 `.well-known` 发现
- **THEN** 取 token 仍指向该显式 `token_url`(由预填的授权服务器元数据提供),认证可正常完成

#### Scenario: 非 oauth2 服务认证行为不变
- **WHEN** 一个 `auth_type: "api_key"` 或 `"none"` 的服务发起请求
- **THEN** 其认证行为与现状一致(api_key 的静态 Bearer 仍经请求头注入),不受 OAuth2 provider 改造影响

### Requirement: access token 过期前自动刷新且对调用透明

平台 SHALL 依据 token 的过期时间在临近或已过期时刷新 access token,刷新由 SDK provider 内部依其取得的 `expires_in` 管理。client_credentials 响应通常不含 refresh token;此时刷新 SHALL 为按 client_credentials 重新取得(即 token 失效后下一请求经 401 反应式重新取 token),平台 MUST NOT 因响应不含 refresh token 而判定刷新失败。刷新成功时对工具调用 MUST 透明(调用方无感知)。平台 MUST NOT 使用已过期的 access token 发起请求(provider 在 token 失效时不主动携带,触发重新取 token)。

#### Scenario: token 过期时自动重新取得并透明完成调用
- **WHEN** 某 `oauth2` 服务的 access token 已过期,此时发起工具调用
- **THEN** provider 不携带过期 token、经 401 反应式重新取得新 token 再重试,调用方拿到正常工具结果,无需感知刷新发生

#### Scenario: 不使用过期 token 发起请求
- **WHEN** access token 已过期且重新取得失败
- **THEN** 平台不使用过期 token 完成调用,转入认证失败处理(瞬时错误可重试,真认证错误标记不可用)

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

