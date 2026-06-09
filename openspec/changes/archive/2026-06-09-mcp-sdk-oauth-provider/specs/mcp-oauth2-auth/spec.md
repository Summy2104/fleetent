## MODIFIED Requirements

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
