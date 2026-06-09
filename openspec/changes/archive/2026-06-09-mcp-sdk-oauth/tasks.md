## 1. `_ClientCredentialsAuth` httpx.Auth 适配器

- [x] 1.1 Write failing tests for `_ClientCredentialsAuth.async_auth_flow`: ① 首次请求挂 `Authorization: Bearer <token>`(token 经 `_resolve_oauth_token` 取得,mock 之);② 请求得 401 → 清缓存 + 刷新 + 对该请求重试一次,第二次挂新 token;③ 非 401 响应不重试 — in tests/unit/test_mcp_sdk_oauth.py(mock `_resolve_oauth_token`,构造假 request/response,驱动 async_auth_flow 生成器)
- [x] 1.2 实现 `_ClientCredentialsAuth(httpx.Auth)`:`__init__(self, server)`;`async_auth_flow`:resolve→挂 Bearer→`yield request`→若 401 则 `_token_store.clear`+resolve+重挂+再 `yield` 一次。薄适配器,token 逻辑全复用 `_resolve_oauth_token`

## 2. 经 SDK transport `auth=` 注入 + `_http_headers` 去 oauth 分支

- [x] 2.1 Write failing tests: ① `_transport_cm` 对 `auth_type="oauth2"` 的 http/sse 传入非 None 的 `_ClientCredentialsAuth`,对 `api_key`/`none` 传 `auth=None`(mock streamablehttp_client/sse_client 捕获 `auth=` kwarg);② `_http_headers` 对 oauth2 服务不再返回 `Authorization`(改由 auth= 注入),对 api_key 仍返回 Bearer — in tests/unit/test_mcp_sdk_oauth.py
- [x] 2.2 加 `_oauth_auth(server)` 工厂(oauth2 返回 `_ClientCredentialsAuth`,否则 None);`_transport_cm` 的 streamablehttp_client/sse_client 传 `auth=_oauth_auth(server)`;`_http_headers` 去掉 oauth bearer 分支(只留自定义 headers + api_key bearer)

## 3. 认证不可用经 auth flow 冒泡的降级处理

- [x] 3.1 Write failing test: 当 token 解析抛 `OAuthAuthUnavailableError`(真实认证失败,sticky 置位)经会话冒泡时,`_call_via_session` 捕获并返回「认证不可用」降级文案;后续调用由上游 `_auth_unavailable` 预检短路 — in tests/unit/test_mcp_sdk_oauth.py
- [x] 3.2 在 `_call_via_session` 与 `_call_utility` 的调用处 catch `OAuthAuthUnavailableError` → 返回现有「authentication unavailable」文案(复用现成构造);sticky/恢复语义不动

## 4. 收尾与门禁

- [x] 4.1 Run `uv run pytest tests/unit/test_mcp_sdk_oauth.py tests/unit/test_mcp_*.py -q`(新增 + 既有 MCP 单测全绿)
- [x] 4.2 `make test-pr` 对照 main 基线,确认无新增失败
- [x] 4.3 `uv run pytest tests/integration -q` 对照 main 基线(隔离验证既有失败集,确认 MCP 无新增)
- [x] 4.4 `uv run mypy src/fleetent/integrations/mcp/client.py`
