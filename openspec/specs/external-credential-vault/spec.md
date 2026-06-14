# external-credential-vault Specification

## Purpose
Define how external services, per-principal credentials, and OAuth consent are
stored and resolved for connector-backed tools.
## Requirements
### Requirement: 外部服务注册表（单层全局，多协议）

系统 SHALL 提供一张外部服务注册表 `external_services`，登记每个可被工具访问的外部服务的非密配置：`service_id`（主键）、`kind`、`protocol`（`oauth2_authcode` | `api_key`）、`authorize_url`、`token_url`、`client_id`、`scopes`、`enabled`、时间戳。注册表 SHALL 为**单层全局**（每个 `service_id` 仅一条，无 per-agent 覆盖层）。`client_secret` MUST NOT 存入该表（走 env / `agent_secrets`）。SQL MUST 用 named parameters 经 store 边界，schema MUST 由迁移建立，无 ORM。

#### Scenario: 注册并读回一个服务
- **WHEN** 管理员注册一个 `service_id="google-drive"`、`protocol="oauth2_authcode"` 的服务
- **THEN** 该服务出现在注册表中，可读回其 authorize/token endpoint、`client_id`、scopes，且不含任何 `client_secret`

#### Scenario: service_id 全局唯一
- **WHEN** 已存在 `service_id="google-drive"` 时再次以同 id 注册
- **THEN** store 拒绝重复（无 per-agent 维度可区分）

### Requirement: per-principal 加密凭证存储

系统 SHALL 提供 `external_credentials` 表，主键 `(user_id, service_id)`，存储该 principal 对该服务的凭证。凭证负载（OAuth token 组 `{access, refresh, expires, scopes}` 或 API key 值）MUST 加密落盘后存入单一密文列，并附 `status`（`authorized` | `needs_consent` | `needs_reauth` | `error`）。明文凭证 MUST NOT 出现在任何返回值、日志或审计中。`user_id` 即 `users.id`，使「per-user 凭证」与未来「agent service-principal 凭证」共用同一主键形状。

#### Scenario: 加密存储与读取
- **WHEN** 为 `(user="u1", service="google-drive")` 写入一组 OAuth token 并随后读取
- **THEN** 落盘列为密文（非明文 token），读取时解密得到原 token，`status=authorized`

#### Scenario: 凭证按 principal 隔离
- **WHEN** `(u1, google-drive)` 已授权而 `(u2, google-drive)` 未授权
- **THEN** 以 u2 解析该服务凭证得到「未授权」，u1 的凭证不被 u2 取得

### Requirement: 加密复用既有 Fernet 主密钥

凭证负载加密 SHALL 复用既有的对称加密机制（Fernet + `FLEETENT_SECRET_KEY`，与 `agent_secrets` 同一套），MUST NOT 引入新的 master key 配置。当 `FLEETENT_SECRET_KEY` 缺失或无效时，写入 / 解密凭证的操作 MUST 抛出清晰错误而非静默降级。

#### Scenario: 缺密钥时拒绝凭证操作
- **WHEN** `FLEETENT_SECRET_KEY` 未设置且尝试写入或解密一条凭证
- **THEN** 操作抛出明确的密钥缺失错误，不写入明文、不返回明文

### Requirement: Vault provider 经 seam 注入并按 principal 解析

系统 SHALL 提供一个 Vault provider，实现既有 `connectors.CredentialProvider` 契约，platform 启动时经 `connectors.set_provider` 注入。被注入后，对声明了 connector 的工具，`get_credential(user_id, service, scopes)` SHALL 查 `external_credentials`：命中有效凭证返回 `Credential`（携带工具所需 client）；无凭证 / `user_id` 缺失返回 `NeedsConsent`。未注入（standalone agent 无 platform）时 seam SHALL 保持默认行为（恒 `NeedsConsent`），且 agent runtime MUST NOT 因此 import platform。

#### Scenario: 已授权用户取到凭证并执行工具
- **WHEN** platform 注入 Vault provider 后，已授权用户 u1 调用一个 `@tool(connector="google-drive")` 的工具
- **THEN** provider 从 `external_credentials` 解析出凭证，dispatch 注入隐藏 `client`，工具执行并返回结果

#### Scenario: 未授权用户短路为 consent
- **WHEN** 未授权用户 u2 调用同一工具
- **THEN** provider 返回 `NeedsConsent`，dispatch 不执行工具，返回携带 consent URL 的提示串

#### Scenario: standalone 无 platform 时退化为待授权
- **WHEN** 未注入 Vault provider（standalone agent）时调用声明 connector 的工具
- **THEN** seam 返回 `NeedsConsent`，且无 `import fleetent.platform.*` 发生

### Requirement: 最小 OAuth2 授权码 consent 流

系统 SHALL 提供 OAuth2 授权码的最小 consent 流：一个 authorize 端点构造带 `state` 的 provider 授权 URL 供用户本人浏览器跳转；一个 callback 端点校验 `state`、以 code 换取 token、加密写入 `external_credentials` 并置 `status=authorized`。首次 consent MUST 由用户本人完成，系统 MUST NOT 提供任何「管理员代为完成首次授权」的路径。

#### Scenario: 用户完成授权后凭证入库
- **WHEN** 用户经 authorize 端点跳转授权并带 code 回到 callback 端点，且 `state` 校验通过
- **THEN** 系统用 code 换取 token、加密写入 `(user_id, service_id)`、置 `status=authorized`，该用户下次调用对应工具不再 `NeedsConsent`

#### Scenario: state 校验失败拒绝写入
- **WHEN** callback 收到的 `state` 与发起时不匹配
- **THEN** 不换取 token、不写入凭证，返回错误

#### Scenario: 无管理员代授权路径
- **WHEN** 检视 consent 流的对外端点
- **THEN** 不存在任何接受「代某用户完成首次 consent」的端点

### Requirement: access token 过期自动刷新

当解析一条 OAuth 凭证而其 access token 已过期、且持有有效 refresh token 时，Vault provider SHALL 先用 refresh token 向 service 的 `oauth_config.token` 换取新 access token，更新现有 `external_credentials.payload_ciphertext` 所承载的加密 JSON 负载并维护标准化 `expires_at`，再返回 `Credential`。现有 store 的真实入口仍是 `put_oauth_credential(user_id, service_id, payload, *, updated_by=None, status=\"authorized\")` 与 `get_credential(user_id, service_id)`；本变更 SHALL 在该签名之上扩展生命周期语义，而非引入新表列。刷新过程 MUST NOT 把 token 明文写入日志 / trace / 异常文本。

#### Scenario: 过期则刷新后返回凭证
- **WHEN** `(u1, gdrive)` 的 access token 已过期但 refresh token 有效，u1 调用对应工具
- **THEN** provider 刷新得到新 access token、更新 `external_credentials` 密文与过期时间，并返回携带有效 client 的 `Credential`

#### Scenario: 未过期不刷新
- **WHEN** access token 仍在有效期内
- **THEN** 直接返回 `Credential`，不触发刷新请求

### Requirement: refresh 失效与错误的状态流转

当 refresh token 已失效（provider 拒绝刷新）时，Vault provider SHALL 置 `status=needs_reauth` 并使解析返回 `NeedsConsent`（携带重新授权 URL）。当刷新因网络等可重试原因失败时，SHALL 置 `status=error` 并使解析返回一个新的 retryable credential error 结果，与当前 seam 中的「未授权/NeedsConsent」语义区分开。

#### Scenario: refresh token 失效需重新授权
- **WHEN** 刷新时 provider 返回 refresh token 失效
- **THEN** `status` 变为 `needs_reauth`，解析返回 `NeedsConsent`，工具短路为重新授权提示

#### Scenario: 刷新网络失败为可重试错误
- **WHEN** 刷新请求遭遇可重试网络错误
- **THEN** `status` 变为 `error`，解析返回 retryable credential error，区别于未授权

### Requirement: 凭证吊销

系统 SHALL 提供吊销一条 `(user_id, service_id)` 凭证的能力：删除本地加密凭证，并尽力调用 provider 的 revoke endpoint（失败仅记日志，不阻断本地删除）。吊销后该 principal 对该服务下次使用 SHALL 回到 `NeedsConsent`。

#### Scenario: 吊销后回到未授权
- **WHEN** 吊销 `(u1, gdrive)` 凭证
- **THEN** 本地凭证被删除、尽力调用外部 revoke，u1 下次调用对应工具返回 `NeedsConsent`

#### Scenario: 外部 revoke 失败不阻断本地删除
- **WHEN** 外部 revoke endpoint 调用失败
- **THEN** 本地凭证仍被删除，失败仅记日志，吊销整体视为完成

### Requirement: 用户提交 API key 凭证

对 `protocol=apikey` 的服务，系统 SHALL 提供「用户本人提交自己的外部服务 API key」的入口。提交的 key SHALL 经 Fernet 加密（复用 `FLEETENT_SECRET_KEY`）写入 `external_credentials` 的 `(user_id, service_id)`，密文负载形态为 `api_key{value}`，`status=authorized`。系统 MUST NOT 提供「管理员代某用户填入 API key」的路径。key 明文 MUST NOT 出现在返回值 / 日志 / trace / 异常文本。

#### Scenario: 用户提交 key 后入库
- **WHEN** 用户为 `protocol=apikey` 的服务 `internal-api` 提交自己的 API key
- **THEN** key 加密写入 `(user_id, "internal-api")`，`status=authorized`，明文不回显

#### Scenario: 无管理员代填路径
- **WHEN** 检视 API-key 提交端点
- **THEN** 不存在接受「代某用户填入 key」的端点

### Requirement: API-key 凭证解析

Vault provider 对 `protocol=apikey` 的服务 SHALL：命中已提交 key 时返回 `Credential`（client 携带该用户的 key）；无 key 时返回 `NeedsConsent`，其提示 SHALL 指向「提交 API key」而非 OAuth 授权跳转。API-key 凭证 SHALL NOT 参与 access-token 刷新流（无 refresh 概念）。

#### Scenario: 有 key 时注入凭证
- **WHEN** 用户已为 `internal-api` 提交 key 并调用对应 `@tool(connector="internal-api")` 工具
- **THEN** provider 返回携带该用户 key 的 `Credential`，dispatch 注入隐藏 client 执行工具

#### Scenario: 无 key 时提示提交
- **WHEN** 用户未提交 `internal-api` 的 key 即调用工具
- **THEN** 返回 `NeedsConsent`，提示指向提交 API key 的入口，不发起 OAuth 跳转

