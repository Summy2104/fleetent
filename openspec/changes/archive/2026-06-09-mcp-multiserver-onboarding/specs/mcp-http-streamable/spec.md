## ADDED Requirements

### Requirement: 自定义 HTTP headers 透传

HTTP 传输的 MCP 服务 SHALL 支持在 agent 配置中声明任意自定义 header(`mcp_servers[*].headers`),平台 MUST 将其逐项并入该服务每个请求的请求头,与 Accept 协商头、`Authorization`(Bearer/api_key)、`Mcp-Session-Id` 等内建头共存。header 值为 `env:VAR_NAME` 形式时 MUST 从进程环境解析为真实值后再发送,绝不发送字面 `env:VAR_NAME`。

#### Scenario: 自定义 header 随请求发送
- **WHEN** 某 `transport: http` 服务声明 `headers: {X-API-Key: "literal-key"}`
- **THEN** 该服务的 initialize / tools/list / tools/call 请求头携带 `X-API-Key: literal-key`

#### Scenario: header 值的 env: 引用被解析
- **WHEN** 某服务声明 `headers: {X-API-Key: env:MIDDLE_KEY}` 且 `MIDDLE_KEY` 在进程环境中已设置
- **THEN** 请求头携带 `X-API-Key` 为 `MIDDLE_KEY` 的解析值,而非字面 `env:MIDDLE_KEY`

#### Scenario: 自定义 header 与内建认证共存
- **WHEN** 某服务同时配置 `auth_type: api_key` / `api_key_env` 与自定义 `headers`
- **THEN** 请求头同时包含 `Authorization` 与声明的自定义 header,互不覆盖

### Requirement: HTTP 请求 URL 原样发送

HTTP 传输的 MCP 请求 SHALL 使用配置的 `url` 原样作为请求目标,MUST NOT 强制追加尾斜杠。这样既支持以 `/mcp` 结尾的严格路径服务,也支持服务端自有的路径规范。

#### Scenario: 严格路径服务不被追加尾斜杠
- **WHEN** 某服务配置 `url: https://host/mcp`(无尾斜杠)
- **THEN** initialize / tools/list / tools/call 的请求目标为 `https://host/mcp`,不是 `https://host/mcp/`

#### Scenario: 配置带尾斜杠时按原样发送
- **WHEN** 某服务配置 `url: https://host/mcp/`(带尾斜杠)
- **THEN** 请求目标为 `https://host/mcp/`,与配置一致
