## 1. SDK provider 子类:preseed + sticky/transient 区分

- [x] 1.1 Write failing tests for `_FleetentClientCredentialsProvider` — in tests/unit/test_mcp_sdk_oauth_provider.py:① 构造后 `_initialize` 预填 `context.oauth_metadata.token_endpoint == server.token_url`(且 `_get_token_endpoint()` 返回它);② client_id/secret(从 env)/scopes/`token_endpoint_auth_method=="client_secret_post"` 正确映射;③ `_handle_token_response` 收到 400+invalid_client → 置 `server._auth_unavailable=True` 且抛 `OAuthAuthUnavailableError`;④ 收到 500 → 交回 super 抛 `OAuthTokenError` 且**不**置 sticky
- [x] 1.2 实现 `_FleetentClientCredentialsProvider(ClientCredentialsOAuthProvider)` + `_FleetentTokenStorage(TokenStorage)`:映射配置、`_initialize` 预填 oauth_metadata(issuer/authz 从 token_url 派生)、覆盖 `_handle_token_response` 区分 sticky/transient

## 2. `_oauth_auth` 改返回 SDK provider + 删 A 机器

- [x] 2.1 Write failing tests:① `_oauth_auth(oauth2 server)` 返回 `_FleetentClientCredentialsProvider` 实例,api_key/none 返回 None;② `_transport_cm` 把它经 `auth=` 传给 streamablehttp_client/sse_client(沿用既有捕获 auth= 的测试手法)— in tests/unit/test_mcp_sdk_oauth_provider.py
- [x] 2.2 改 `_oauth_auth` 返回新 provider;删 `_ClientCredentialsAuth`/`_resolve_oauth_token`/`_fetch_client_credentials_token`/`_token_is_valid`/`_is_auth_error_response`/`_is_transient_token_error`/fleetent `OAuthToken`/`_InMemoryTokenStore`/`_token_store`+`_refresh_lock` 字段/TTL 常量;保留 `_auth_unavailable`/`_clear_oauth_auth_state`/`OAuthAuthUnavailableError`

## 3. 调用路径错误映射(sticky 副作用 + 瞬时降级)

- [x] 3.1 Write failing tests — in tests/unit/test_mcp_sdk_oauth_provider.py:① 会话调用使 `server._auth_unavailable` 被置位(模拟 D4 副作用)后冒泡 → `_call_via_session` 返回"认证不可用"降级、不抛、后续调用上游短路;② 瞬时 `OAuthTokenError` 冒泡 → 返回降级、**不**置 sticky、不崩
- [x] 3.2 在 `_call_via_session` 与 `_call_utility` 实现 D5 映射:先查 sticky 副作用 → auth 降级;再瞬时 SDK OAuth 错误 → 降级不 sticky;再断线 → 懒重连;否则抛

## 4. 端到端流程验证(httpx MockTransport,真实 SDK provider)

- [x] 4.1 Write failing/then-green integration-style test — in tests/unit/test_mcp_sdk_oauth_provider.py:用 httpx.AsyncClient(auth=provider, transport=MockTransport) 模拟序列「首请求无 token→401(带 WWW-Authenticate)→.well-known 探测 404→token 端点 200 返回 access_token→重试 200」,断言:重试请求带 `Authorization: Bearer <token>`、token POST 命中预填 token_url、body 为 grant_type=client_credentials + client_secret_post

## 5. 收尾与门禁

- [x] 5.1 Run `uv run pytest tests/unit/test_mcp_sdk_oauth_provider.py tests/unit/test_mcp_*.py -q`(新 + 既有 MCP 单测全绿)
- [x] 5.2 `make test-pr` 对照 main 基线,无新增失败
- [x] 5.3 `uv run pytest tests/integration/test_mcp_client.py -q`(MCP 集成绿);全量 integration 既有失败经隔离对照确认无新增
- [x] 5.4 `uv run mypy src/fleetent/integrations/mcp/client.py`
