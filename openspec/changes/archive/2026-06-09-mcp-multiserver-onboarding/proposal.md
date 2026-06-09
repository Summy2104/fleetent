## Why

接入一批真实 MCP server(Atlassian jira/confluence/bitbucket、knowledge-bridge、armada、middle、google-drive 等)时暴露了 fleetent MCP 客户端的几处接入障碍:

1. **npm 包名被误判为 secret**:`_reject_inline_secrets` 把 `args` 里的 `@aashari/mcp-server-atlassian-jira` 当成 inline secret 拒绝加载。
2. **secret 无法用 .env 引用**:stdio env 和 HTTP header 里的 token 只能写字面值(会被 secret 扫描拒绝),无法像 `*_env` 那样引用 .env。
3. **HTTP MCP 不支持自定义 header**:`McpServerSettings` 没有 `headers` 字段,使用 `X-API-Key` 认证的 server(如 middle)无法接入——而自定义 headers 是 4 个主流 MCP 客户端(claude-code/opencode/hermes/openclaw)的一致标准做法。
4. **URL 强制加尾斜杠**:客户端拼接 `f"{server.url}/"`,导致严格路径的 server(knowledge-bridge)返回 404。
5. **协议版本停在 2025-06-18**:官方 current 已是 2025-11-25。

## What Changes

- **修改** `_reject_inline_secrets`:跳过非敏感字段(`args`/`command`/`id`/`transport`),保留对 `url` 的扫描(URL 可能嵌 token)
- **新增** `env:VAR_NAME` 引用语法:在 agent.yaml 任意字段(尤其 `mcp_servers[*].env` 和 `mcp_servers[*].headers` 值)可写 `env:VAR`,运行时从进程环境(.env)解析
- **新增** `McpServerSettings.headers` 字段:HTTP MCP 自定义 header,运行时逐项透传;header 值支持 `env:` 引用解析
- **修改** HTTP 请求 URL:使用配置的 `url` 原样发送,不再强制加尾斜杠
- **修改** `PROTOCOL_VERSION` `2025-06-18` → `2025-11-25`(临时手段:手写客户端无法自动跟进版本;待 MCP SDK 迁移后改用 `LATEST_PROTOCOL_VERSION`)

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `file-agent-runtime`: inline-secret 扫描收紧范围 + 接受 `env:VAR` 引用语法
- `mcp-stdio-isolation`: stdio 子进程 env 解析 `env:` 引用
- `mcp-http-streamable`: 支持自定义 HTTP headers(含 env: 解析);HTTP 请求 URL 原样发送

## Impact

- `src/fleetent/agent_config.py`:`_reject_inline_secrets` 范围、`_is_env_reference` 接受 env:
- `src/fleetent/config.py`:`McpServerSettings` 新增 `headers`
- `src/fleetent/runtime/agent_app.py`:透传 `headers`
- `src/fleetent/integrations/mcp/client.py`:`_subprocess_env` + `_base_headers` 解析 env:、URL 原样、协议版本
- `tests/unit/`:新增/扩充测试
- 无新依赖
- 完全向后兼容(新字段默认空,旧配置不受影响)
