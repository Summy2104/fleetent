## Context

fleetent MCP 客户端手写了 HTTP 传输层(stdio 用官方 SDK)。接入真实 server 时发现 secret 引用、自定义 header、URL 处理、协议版本几处缺口。这些是接入层修复,不触及协议核心;MCP SDK 迁移是后续独立项。

`McpServerConfig`(client.py)已有 `headers` 字段且 `_base_headers` 已使用,只是 `McpServerSettings`(agent.yaml schema)未暴露;`_ENV_VAR_NAME_RE` 已含可选 `env:` 前缀。本 change 把这些"半成品"接通。

## Goals / Non-Goals

**Goals:**
- 主流 npm-based MCP server 开箱接入(args 不被误判)
- secret 走 .env 引用(env:VAR),覆盖 stdio env 与 HTTP header
- X-API-Key 类 server 可接入(自定义 header)
- 严格路径 server 可接入(URL 原样)
- 协议版本对齐官方 current

**Non-Goals:**
- 不迁移官方 MCP SDK(独立项)
- 不加 SSE 传输、OAuth PKCE(独立项)
- 不引入 `${VAR}` 语法(保持 fleetent 既有 `env:` 约定;迁移期不扩面)

## Decisions

### D1:inline-secret 扫描跳过 args/command/id/transport,保留 url
真正误判的只有 `args`(npm 包名)。`command`/`id`/`transport` 不可能是 secret,一并跳过。**保留 `url` 扫描**——URL 可能嵌 `?token=` 形式的密钥,跳过会留安全洞。

### D2:env: 解析在 client.py 的 point-of-use(而非 agent_app 构建处)
`_subprocess_env`(stdio)与 `_base_headers`(http)各自解析 `env:` 引用,共用 `_resolve_env_ref()`。好处:无论 `McpServerConfig` 由谁构建(agent_app / platform / 测试),解析都生效;client.py 自包含。`env:FOO` → `os.environ["FOO"]`(缺失取空串,与现有 api_key_env 缺失语义一致由上层处理)。

### D3:headers 透传 + env: 解析
`McpServerSettings.headers: dict[str,str]` → agent_app 透传给 `McpServerConfig.headers` → `_base_headers` 逐项解析 env: 后并入请求头。与 Bearer/api_key 并存(Authorization 优先级不变)。

### D4:协议版本硬钉 2025-11-25(临时)
手写客户端无 SDK 的 `LATEST_PROTOCOL_VERSION` 可读,只能硬钉。标注为临时:SDK 迁移后此常量删除,改读 SDK。

## Risks / Trade-offs

- **[Risk] env: 在未解析的字段被当字面值** → 解析只在 stdio env / http header 两个 point-of-use 发生;其它字段不支持 env:,inline-secret 扫描对其它字段的 env: 仍按"非 secret-like"放行(`env:` 前缀的值不像 secret)。文档明确 env: 仅用于 mcp env/headers。
- **[Risk] 协议版本硬钉会过时** → 已标注临时,SDK 迁移项接管。
- **[兼容] 全部新增字段默认空** → 旧 agent.yaml 零改动。
