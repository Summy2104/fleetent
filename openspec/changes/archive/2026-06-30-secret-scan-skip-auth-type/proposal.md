## Why

agent.yaml 加载时的 inline-secret 守卫 `agent_config._reject_inline_secrets` 会扫描 `mcp_servers` 各字符串值，对"像密钥"的值（`looks_inline_secret`）报错。但 **`auth_type` 是判别枚举（discriminator），永远不是 secret**——而 `looks_inline_secret('oauth_authorization_code')` 与 `looks_inline_secret('oauth_client_credentials')` **误判为 True**，且 `auth_type` 不以 `_env` 结尾、不被 env-引用豁免。结果：任何**经连接器物化**出顶层 `auth_type: oauth_authorization_code`（或 `oauth_client_credentials`）的 agent，加载 agent.yaml 时直接抛 `ValueError: inline secret-like value ... at 'mcp_servers.N.auth_type'`，**agent 无法启动**。此前未暴露是因为 oauth 类型多经 config_overrides 的 `x-fleetent.auth`（顶层 auth_type=None）配置；连接器路径物化顶层 auth_type 后首次触发。修复：把结构性判别字段 `auth_type` 加入 secret 扫描跳过集（与既有的 `.transport` / `.command` / `.id` / `.args.` 同类）。

## What Changes

- `agent_config._SKIP_SECRET_SCAN_SEGMENTS` 新增 `.auth_type`，使 `_reject_inline_secrets` **不扫描** `auth_type` 判别枚举值。
- 不改 secret 检测启发式 `looks_inline_secret`，不放宽对真正 secret 字段的扫描（`client_secret_env` 等仍经 `_env` 豁免、token_url/authorization_endpoint/scope 等仍被扫描）。
- 纯结构字段豁免，行为最小变更。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `mcp-auth-config`: 明确 `auth_type` 判别枚举为**结构性非密字段**，agent.yaml 加载时的 inline-secret 守卫 SHALL NOT 因其值（如 `oauth_authorization_code` / `oauth_client_credentials`）误报为 inline secret；连接器物化出顶层 `auth_type` 的 agent SHALL 能正常加载/启动。

## Impact

- **受影响代码**：`src/fleetent/agent_config.py`（`_SKIP_SECRET_SCAN_SEGMENTS` 增一项）。
- **Public API surface**：无（内部守卫行为）。
- **owning packages**：agent runtime（`agent_config`）。
- **owned tables**：无。**config namespace**：无。
- **cross-module deps**：无新增。
- **migration / shim plan**：无（纯结构字段豁免；不影响对真正 secret 的扫描）。
- **修复效果**：连接器配置的 `oauth_authorization_code` / `oauth_client_credentials` MCP server 物化后 agent 可正常启动（此前 boot 崩溃）。
