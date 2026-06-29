# connector-credential-injection Specification

## Purpose
TBD - created by archiving change connector-credential-injection. Update Purpose after archive.
## Requirements
### Requirement: connector 凭证接口

系统 SHALL 提供 `connectors` 模块，定义 `Credential`、`NeedsConsent` 与 `CredentialError` 三种结果类型及统一入口 `get_credential(user_id, connector, scopes)`。该入口 MUST 委派给一个可替换的 provider，使凭证来源可在测试中注入，而不发起真实外部请求。

#### Scenario: provider 返回已授权凭证
- **WHEN** 以已授权用户调用 `get_credential` 且 provider 持有有效凭证
- **THEN** 返回一个 `Credential`，其中携带工具执行所需的 client

#### Scenario: 缺少授权时返回待授权
- **WHEN** 以未授权用户（或 `user_id` 缺失）调用 `get_credential`
- **THEN** 返回一个 `NeedsConsent`，携带 connector 名与 consent URL，且不返回任何凭证

#### Scenario: 凭证刷新不可恢复失败时返回错误
- **WHEN** provider 持有凭证但刷新失败（网络错误或 HTTP 非 2xx）
- **THEN** 返回一个 `CredentialError`，携带 `message` 与 `retryable` 标志，且不返回任何 client

### Requirement: @tool 声明 connector 与 scopes

`@tool` 装饰器 SHALL 接受可选的 `connector` 与 `scopes` 声明，并记录到独立的 connector 元数据，供 dispatch 查询。该元数据 MUST NOT 出现在 `get_schemas()` 返回的 LLM 可见 JSON Schema 中。

#### Scenario: 声明 connector 的工具被记录
- **WHEN** 一个工具以 `@tool(connector="google-drive", scopes=["drive.readonly"])` 注册
- **THEN** 通过 connector 元数据查询该工具可得到其 connector 名与 scopes

#### Scenario: connector 声明不进 LLM schema
- **WHEN** 对声明了 connector 的工具调用 `get_schemas()`
- **THEN** 返回的 schema 中不包含 connector / scopes 信息

### Requirement: dispatch 注入已授权凭证

当被调用工具声明了 connector 时，`dispatch` SHALL 先调用 `connectors.get_credential`。若返回 `Credential`，dispatch MUST 将其 client 作为隐藏的 keyword-only 参数 `client` 注入工具调用；该 `client` 参数 MUST NOT 出现在 LLM 可见的工具 schema 中。

#### Scenario: 已授权时注入 client 并执行工具
- **WHEN** dispatch 一个声明了 connector 的工具且 `get_credential` 返回 `Credential`
- **THEN** 工具以注入的隐藏 `client` 参数被执行，并返回工具结果

#### Scenario: 隐藏 client 参数不进 schema
- **WHEN** 工具签名为 `def t(query: str, *, client)` 且对其调用 `get_schemas()`
- **THEN** 返回 schema 的参数中只有 `query`，不包含 `client`

#### Scenario: 无 connector 声明的工具行为不变
- **WHEN** dispatch 一个未声明 connector 的工具
- **THEN** 不调用 `get_credential`，工具按现状直接执行并返回结果

### Requirement: 未授权时短路返回 consent

当被调用工具声明了 connector 且 `get_credential` 返回 `NeedsConsent` 时，`dispatch` MUST 短路：不执行工具函数，并返回包含 consent URL 的提示串给 LLM。

#### Scenario: 待授权时不执行工具
- **WHEN** dispatch 一个声明了 connector 的工具且 `get_credential` 返回 `NeedsConsent`
- **THEN** 工具函数不被调用，dispatch 返回包含 consent URL 的提示串

### Requirement: 凭证刷新失败时短路返回可重试错误

当被调用工具声明了 connector 且 `get_credential` 返回 `CredentialError` 时，`dispatch` MUST 短路：不执行工具函数，并返回包含错误描述与 retryable 标志的提示串给 LLM。`CredentialError` 与 `NeedsConsent` 的短路路径相互独立：前者描述"凭证暂时不可用，可重试"，后者描述"需要先完成授权"。

#### Scenario: 刷新失败时不执行工具
- **WHEN** dispatch 一个声明了 connector 的工具且 `get_credential` 返回 `CredentialError(retryable=True)`
- **THEN** 工具函数不被调用，dispatch 返回包含错误描述与 retryable 标志的提示串

#### Scenario: CredentialError 与 NeedsConsent 短路路径独立
- **WHEN** `get_credential` 返回 `CredentialError` 而非 `NeedsConsent`
- **THEN** dispatch 返回错误描述（而非 consent URL），两条路径互不混用

### Requirement: 凭证不泄漏

注入的凭证（`client` 及 `Credential` 中的 secret）MUST NOT 出现在 dispatch 的返回值、运行日志（trace）、异常文本或 LLM 可见 schema 中。

#### Scenario: 凭证不进 dispatch 返回值与 trace
- **WHEN** 一个声明了 connector 的工具被注入 `client` 后执行
- **THEN** dispatch 返回值与写入 trace 的工具参数 / 结果中均不包含该 client 或其 secret

#### Scenario: 凭证不进异常文本
- **WHEN** 凭证注入或工具执行过程中抛出异常
- **THEN** 异常文本中不包含凭证 secret

### Requirement: seam 在 platform vault 退役后安全降级

工具凭证的 platform 管理面退役后，`connectors.py` seam 与 `@tool(connector=)` 通道 SHALL 保留。若未注入任何 provider，`get_credential(...)` MUST 经默认 provider 返回 `NeedsConsent`，而不是抛错或中断 agent 运行。

#### Scenario: 未注入 provider 时 connector 工具优雅短路
- **WHEN** 一个声明 `@tool(connector="github")` 的工具被调度，且当前没有任何 provider 注入
- **THEN** 调度返回 consent 提示，工具函数不执行，agent 运行不中断

#### Scenario: 无 platform、无管理库表环境仍可完成对话
- **WHEN** 在无 platform、管理库表不存在的环境执行 `fleetent agent run`
- **THEN** connector seam 可正常 import，凭证类工具降级为 `NeedsConsent`，对话仍可完成
