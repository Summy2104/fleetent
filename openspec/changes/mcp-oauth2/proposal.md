## Why

MCP1（mcp-http-streamable，已合入）的标准 HTTP 传输只支持两种认证：`auth_type: "none"` 与 `auth_type: "api_key"`（从 `api_key_env` 读环境变量，附加 `Authorization: Bearer <key>`，见 `_base_headers` mcp_client.py 行 166-175）。`McpServerConfig.auth_type` 字段已预留 `"oauth2"` 取值（行 34 注释 `"none" | "api_key" | "oauth2"`），但**无任何 OAuth2 实现**——声明 `auth_type: "oauth2"` 的服务今天接不进来。docs/capabilities/mcp.md 把「OAuth2 认证」列为 v1.0 规划项（`[ ]`）：「Token 过期时自动刷新；认证失败时标记服务不可用并提示重新授权」。

越来越多的企业内 MCP 服务（自托管的网关、内部 SaaS 的 on-prem 版）要求 OAuth2 而非静态 API Key——静态长期 key 难轮转、难审计、泄漏面大。平台需要能用 OAuth2 拿短时 access token、过期前自动刷新，才能接入这类服务。

这是 MCP5（OAuth2 认证），建立在 MCP1 之上。**关键约束：必须可自托管**——OAuth2 的 token 端点是客户内网自己的授权服务器（或自托管 IdP，如 Keycloak），平台只作为 OAuth2 客户端按标准协议取 token，**绝不依赖云专有身份服务**（违反数据主权原则）。token 存储必须可注入、可隔离测试。本 change 聚焦**对 MCP server 的 OAuth2 认证与 token 生命周期**，不碰会话管理（MCP2）与健康重连（MCP3）。

## What Changes

- **OAuth2 客户端认证（client_credentials 优先）**：`auth_type: "oauth2"` 的服务，平台按 OAuth2 标准向配置的 **token 端点**（客户内网自托管授权服务器）请求 access token，并以 `Authorization: Bearer <access_token>` 附加到对该 MCP server 的请求头。首选 `client_credentials` 授权类型（服务到服务、无人值守，适配 on-prem 无头部署）。
- **Token 自动刷新**：access token 临近/已过期时（依 `expires_in`）自动刷新——**主路径为重跑 client_credentials**（RFC 6749 §4.4 下 client_credentials 响应通常不含 refresh_token，凭据在手直接重取即可）；`refresh_token` 仅作防御性附注（若授权服务器非标准返回则优先用之），缺失时不视为失败、直接重取。刷新对工具调用透明；获取/刷新失败不静默使用过期 token。
- **Token 存储可注入、可隔离**：access token（及过期时间、可选 refresh token）的存储位置可注入（默认内存，按 server 隔离；若需持久化用 aiosqlite 裸 SQL，路径可 monkeypatch），不进模块级可变全局，测试隔离到 `tmp_path`。
- **认证失败处理**：token 获取/刷新返回认证错误（如 token 端点 401/`invalid_client`）时，标记该服务认证不可用并提示「需重新授权 / 检查 OAuth2 凭据」，不反复无效重试打爆 token 端点。
- **配置扩展（self-hostable）**：`config/mcp.yaml` 的 per-server 增加 OAuth2 字段——token 端点 URL、client_id、client_secret（经环境变量引用，不明文入库）、scope（可选）。token 端点指向客户内网授权服务器，无云托管依赖。
- **复用 MCP1 地基**：OAuth2 只替换 `Authorization` 头的来源（从静态 env key 换为动态 access token）；`initialize` / `tools/list` / `tools/call`、SSE/JSON 解析、`{server_id}__{tool_name}` 命名空间、`register_all` 降级均不变。注意取/刷新 token 是 async，而 `_base_headers(server) -> dict` 当前为同步函数：本 change 在请求构造前先 `await` resolve token、再传入头拼装（保持 `_base_headers` 同步），不是同步函数内直接换值（详见 design D6a）。

## Capabilities

### New Capabilities
- `mcp-oauth2-auth`: 对 MCP server 的 OAuth2 认证——`auth_type: "oauth2"` 服务向客户内网自托管 token 端点按 OAuth2（首选 client_credentials）取 access token 并以 Bearer 附加；access token 过期前自动刷新，对调用透明；token 存储按 server 隔离、可注入、可隔离测试；token 获取/刷新认证失败时标记服务认证不可用并提示重新授权，不反复无效重试。无云托管身份依赖，满足数据主权。

### Modified Capabilities
<!-- 不修改既有 spec 的需求级行为。mcp-http-streamable 主 spec 未约束 oauth2（仅实现 none/api_key），auth_type 的 "oauth2" 取值为预留；本 change 以 New Capabilities 承载 OAuth2 行为。none/api_key 认证可观察行为不变。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/mcp_client.py`：
    - `auth_type == "oauth2"` 时为请求附加动态 access token：因取/刷新 token 是 async 而 `_base_headers` 同步，在请求构造前 `await` resolve token 再传入 `_base_headers` 拼装（D6a 首选方案 a，保持 `_base_headers` 同步），其余 `none`/`api_key` 分支不变。
    - 引入 OAuth2 token 获取/刷新逻辑（按 OAuth2 标准向 token 端点 POST，解析 `access_token` / `expires_in` / 可选 `refresh_token`）；token 存储按 server 隔离持有（不进全局可变状态），存储后端可注入。
    - `McpServerConfig` 增加 OAuth2 配置字段（token 端点、client_id、client_secret env 引用、scope），与既有 `auth_type` / `api_key_env` 风格一致。
  - 可能新增轻量 token 存储模块（若持久化）：用 aiosqlite 裸 SQL，`DB_PATH` 可 monkeypatch（遵循 user_store 等既有模式）；默认内存存储则无需新模块。
- **配置**：`config/mcp.yaml` per-server 新增 OAuth2 字段（token_url、client_id、client_secret_env、scope）；`config/mcp.yaml.example` 补 oauth2 示例。token 端点为客户内网授权服务器地址，无云托管专有服务。
- **测试**：扩展 `tests/test_mcp_client.py`（及如有 token 存储模块则新增其测试），用例覆盖：oauth2 服务取 token 并以 Bearer 附加、token 过期自动刷新、刷新对工具调用透明、获取/刷新认证失败标记服务认证不可用并提示重新授权、token 存储按 server 隔离。token 端点 HTTP 用 `respx` mock，**不发真实请求**；token 存储隔离到 `tmp_path`（如持久化）或内存（按 server 隔离）。
- **新依赖说明**：优先**不引入** OAuth2 库——`client_credentials` 是「向 token 端点 POST 表单、解析 JSON」的简单流程，复用 `httpx`（MCP1 已用）手写即可，避免新依赖（CLAUDE.md 新依赖须讨论）。若实现中确需 OAuth2 库（如 `authlib`），须在 design/PR 说明必要性并确认其纯客户端、无云托管依赖、可自托管 token 端点对接；本 change 默认方案为无新依赖手写 client_credentials。
- **不影响**：`auth_type: "none"` / `"api_key"` 既有行为、stdio 传输、命名空间格式、`register_all` 降级、MCP2 会话管理、MCP3 健康重连。
- **数据主权**：token 端点指向客户内网自托管授权服务器（或自托管 IdP），平台仅作 OAuth2 客户端，**禁止**对接 Pinecone Cloud / 云专有身份服务等违反数据主权的组件。
