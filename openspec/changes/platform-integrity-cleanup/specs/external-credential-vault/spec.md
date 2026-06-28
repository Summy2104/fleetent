# external-credential-vault

## ADDED Requirements

### Requirement: 禁用的外部服务在凭证解析被门控
当外部服务 `external_services.enabled=false` 时,Vault provider 的凭证解析链(OAuth 与 api-key 两路)SHALL NOT 返回可用的 `Credential`;无论该 (user, service) 是否已有 `status=authorized` 的凭证,解析 SHALL 返回"未授权"等价结果(与缺凭证一致的 `NeedsConsent` 风格,不抛异常打断调用方)。即管理员禁用某服务后,即便存量绑定/凭证仍在,工具也无法再经该服务取得凭证。

#### Scenario: 启用服务正常解析
- **WHEN** 服务 `internal-api` `enabled=true`,用户已为其提交/授权凭证,并调用对应工具
- **THEN** provider 返回携带凭证的 `Credential`,工具正常执行

#### Scenario: 禁用服务被门控
- **WHEN** 服务 `internal-api` 被设为 `enabled=false`,而用户此前已有该服务的 `authorized` 凭证
- **THEN** provider 不返回可用 `Credential`,而是返回"未授权"等价结果(不注入凭证、不发起调用)

#### Scenario: 门控不打断调用方
- **WHEN** 凭证解析命中禁用服务
- **THEN** 以与"缺凭证"一致的返回形态处理(NeedsConsent 风格),不向调用方抛异常
