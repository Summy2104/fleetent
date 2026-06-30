## MODIFIED Requirements

### Requirement: 运行时错误归一化为固定分类

错误分类层 SHALL 提供 `classify()` 函数，将运行时异常归一化为一组固定分类码：`rate_limit` / `context_overflow` / `tool_timeout` / `tool_crash` / `mcp_disconnect` / `sandbox_oom` / `sandbox_timeout` / `auth_failed` / `llm_timeout` / `unknown`。其中 `llm_timeout` 表示对 LLM 端点的 HTTP 请求层超时或连接错误（区别于 `tool_timeout` 这一 await 层工具超时）。任何无法匹配已知分类的异常 MUST 归类为 `unknown`。

#### Scenario: 限流错误归类为 rate_limit
- **WHEN** `classify()` 接收到限流异常（`RateLimitError` 或状态码 429/503）
- **THEN** 返回的分类码为 `rate_limit`

#### Scenario: 认证错误归类为 auth_failed
- **WHEN** `classify()` 接收到认证失败异常（状态码 401/403）
- **THEN** 返回的分类码为 `auth_failed`

#### Scenario: LLM 请求超时/连接错误归类为 llm_timeout
- **WHEN** `classify()` 接收到 LLM 请求层超时或连接异常（`httpx.ReadTimeout` / `httpx.TimeoutException` / `openai.APITimeoutError` / `openai.APIConnectionError`）
- **THEN** 返回的分类码为 `llm_timeout`，而非 `unknown`

#### Scenario: 未知错误归类为 unknown
- **WHEN** `classify()` 接收到不匹配任何已知分类的异常
- **THEN** 返回的分类码为 `unknown`

### Requirement: 每个分类挂载恢复策略标志位

每个分类码 SHALL 关联一组恢复策略标志位：`should_retry`（是否重试）、`should_compress`（是否触发压缩后重试）、`should_switch_model`（是否切换备用模型）。标志位 MUST 来自单一的分类表，对同一分类码的查询结果一致。

#### Scenario: rate_limit 标志位指示切换模型并重试
- **WHEN** 查询 `rate_limit` 分类的标志位
- **THEN** `should_retry` 为真且 `should_switch_model` 为真

#### Scenario: llm_timeout 标志位指示重试并可切换模型
- **WHEN** 查询 `llm_timeout` 分类的标志位
- **THEN** `should_retry` 为真且 `should_switch_model` 为真（`should_compress` 为假）

#### Scenario: auth_failed 标志位指示不重试
- **WHEN** 查询 `auth_failed` 分类的标志位
- **THEN** `should_retry` / `should_compress` / `should_switch_model` 均为假

#### Scenario: context_overflow 标志位指示压缩后重试
- **WHEN** 查询 `context_overflow` 分类的标志位
- **THEN** `should_compress` 为真

### Requirement: 预留分类码不被主动返回

分类层 SHALL 定义波次 2 错误源的分类码（`tool_timeout` / `mcp_disconnect` / `sandbox_oom` / `sandbox_timeout`）及其标志位，但在未接入对应错误源前，`classify()` MUST NOT 对当前主循环可达的异常返回这些预留分类码。

#### Scenario: 预留分类码已定义且带标志位
- **WHEN** 查询任一预留分类码（如 `mcp_disconnect`）的标志位
- **THEN** 分类表中存在该分类码及其完整标志位定义

#### Scenario: 当前可达异常不产出预留分类码
- **WHEN** `classify()` 接收当前主循环可能抛出的 LLM 调用异常
- **THEN** 返回的分类码仅为本次可判定的分类（`rate_limit` / `context_overflow` / `auth_failed` / `tool_crash` / `llm_timeout` / `unknown`），不为任何预留分类码
