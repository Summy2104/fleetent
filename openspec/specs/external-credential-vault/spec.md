# external-credential-vault Specification

## ADDED Requirements

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
