## ADDED Requirements

### Requirement: connector 凭证接口

系统 SHALL 提供 `connectors` 模块，定义 `Credential` 与 `NeedsConsent` 两种结果类型及统一入口 `get_credential(user_id, connector, scopes)`。该入口 MUST 委派给一个可替换的 provider，使凭证来源可在测试中注入，而不发起真实外部请求。

#### Scenario: provider 返回已授权凭证
- **WHEN** 以已授权用户调用 `get_credential` 且 provider 持有有效凭证
- **THEN** 返回一个 `Credential`，其中携带工具执行所需的 client

#### Scenario: 缺少授权时返回待授权
- **WHEN** 以未授权用户（或 `user_id` 缺失）调用 `get_credential`
- **THEN** 返回一个 `NeedsConsent`，携带 connector 名与 consent URL，且不返回任何凭证

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

### Requirement: 凭证不泄漏

注入的凭证（`client` 及 `Credential` 中的 secret）MUST NOT 出现在 dispatch 的返回值、运行日志（trace）、异常文本或 LLM 可见 schema 中。

#### Scenario: 凭证不进 dispatch 返回值与 trace
- **WHEN** 一个声明了 connector 的工具被注入 `client` 后执行
- **THEN** dispatch 返回值与写入 trace 的工具参数 / 结果中均不包含该 client 或其 secret

#### Scenario: 凭证不进异常文本
- **WHEN** 凭证注入或工具执行过程中抛出异常
- **THEN** 异常文本中不包含凭证 secret
