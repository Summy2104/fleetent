# external-credential-vault Specification

## ADDED Requirements

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
