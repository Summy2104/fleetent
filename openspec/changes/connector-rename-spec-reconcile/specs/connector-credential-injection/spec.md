# connector-credential-injection Specification

## MODIFIED Requirements

### Requirement: connector 凭证接口

系统 SHALL 提供 `connectors` 模块，定义 `Credential`、`NeedsConsent` 与 `CredentialError` 三种结果类型及统一入口 `get_credential(user_id, connector, scopes)`。该入口 MUST 委派给一个可替换的 provider，使凭证来源可在测试中注入，而不发起真实外部请求。

> P7 勘误：P2（oauth-token-lifecycle）实现了第三态 `CredentialError`（刷新失败时返回），当时仅改了代码，未同步回 spec。本次补入。

#### Scenario: provider 返回已授权凭证
- **WHEN** 以已授权用户调用 `get_credential` 且 provider 持有有效凭证
- **THEN** 返回一个 `Credential`，其中携带工具执行所需的 client

#### Scenario: 缺少授权时返回待授权
- **WHEN** 以未授权用户（或 `user_id` 缺失）调用 `get_credential`
- **THEN** 返回一个 `NeedsConsent`，携带 connector 名与 consent URL，且不返回任何凭证

#### Scenario: 凭证刷新不可恢复失败时返回错误
- **WHEN** provider 持有凭证但刷新失败（网络错误或 HTTP 非 2xx）
- **THEN** 返回一个 `CredentialError`，携带 `message` 与 `retryable` 标志，且不返回任何 client

## ADDED Requirements

### Requirement: 凭证刷新失败时短路返回可重试错误

当被调用工具声明了 connector 且 `get_credential` 返回 `CredentialError` 时，`dispatch` MUST 短路：不执行工具函数，并返回包含错误描述与 retryable 标志的提示串给 LLM。`CredentialError` 与 `NeedsConsent` 的短路路径相互独立：前者描述"凭证暂时不可用，可重试"，后者描述"需要先完成授权"。

#### Scenario: 刷新失败时不执行工具
- **WHEN** dispatch 一个声明了 connector 的工具且 `get_credential` 返回 `CredentialError(retryable=True)`
- **THEN** 工具函数不被调用，dispatch 返回包含错误描述与 retryable 标志的提示串

#### Scenario: CredentialError 与 NeedsConsent 短路路径独立
- **WHEN** `get_credential` 返回 `CredentialError` 而非 `NeedsConsent`
- **THEN** dispatch 返回错误描述（而非 consent URL），两条路径互不混用
