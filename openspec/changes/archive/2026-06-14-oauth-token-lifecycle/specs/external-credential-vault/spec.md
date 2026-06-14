# external-credential-vault Specification

## ADDED Requirements

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
