## Why

After the `mcp-sdk-transport` migration, the OAuth2 bearer is resolved once at session-open and baked into the persistent SDK transport's `headers=`. It is never refreshed per-request. Before that migration, the hand-written HTTP path created a fresh client per call and re-resolved the bearer every time, so an expired token refreshed automatically. The persistent SDK session therefore introduced a regression: for a long-lived agent talking to an OAuth2 HTTP/SSE MCP server with a finite token TTL (e.g. ~1h `client_credentials`), calls start failing once the token expires — a mid-session `401` is an `HTTPStatusError`, which is not classified as a disconnect, so neither per-request refresh nor lazy-reconnect recovers it.

The SDK's `OAuthClientProvider` cannot help here: it only implements `authorization_code`+PKCE (+`refresh_token`), requiring an interactive redirect/callback. fleetent's OAuth is machine-to-machine `client_credentials` against a self-hosted authorization server — no human, no redirect. The fix is to inject auth through the SDK transport's `auth=` (an `httpx.Auth`) so token attachment runs per-request, the SDK-idiomatic way.

## What Changes

- Add `_ClientCredentialsAuth(httpx.Auth)` — a thin adapter implementing `async_auth_flow`: attach `Authorization: Bearer <token>` per request, and on a `401` clear the cached token, refresh once, and retry the request once.
- Wire it via the SDK transport `auth=` parameter for `oauth2` http/sse servers in `_transport_cm`; `api_key` / `none` / stdio keep `auth=None` (unchanged).
- Stop resolving the OAuth bearer in `_http_headers` — it keeps only custom `env:`-resolved headers and the static `api_key` bearer. The OAuth bearer moves to the `auth=` object.
- `_call_via_session` catches `OAuthAuthUnavailableError` bubbling from the auth flow and returns the existing "authentication unavailable" degraded text (subsequent calls short-circuit on the sticky `_auth_unavailable` flag, as today).
- Keep the hand-written `client_credentials` token POST and per-server token cache / refresh lock / sticky `_auth_unavailable` / `OAuthAuthUnavailableError` / `_clear_oauth_auth_state` — the SDK has no `client_credentials` grant, so the token fetch stays, just wrapped by the new `httpx.Auth`.

Non-goals (YAGNI): no `authorization_code`/PKCE, no `OAuthClientProvider`, no change to api_key/stdio paths, no change to token-cache or sticky-unavailable semantics.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `mcp-oauth2-auth`: the bearer is injected through the SDK transport's `auth=` (a per-request `httpx.Auth`) with in-session `401` refresh+retry, instead of being resolved once into the session's static `headers=`. The `client_credentials` token POST remains hand-rolled (the SDK lacks that grant).

## Impact

- Code: `src/fleetent/integrations/mcp/client.py` (new `_ClientCredentialsAuth`; `_transport_cm` passes `auth=`; `_http_headers` drops the oauth branch; `_call_via_session` catches `OAuthAuthUnavailableError`).
- Behavior: oauth2 HTTP/SSE servers refresh tokens per-request and recover from mid-session expiry without reopening the session; long-lived sessions no longer wedge after token TTL.
- No dependency changes (`httpx` already present; SDK `auth=` already accepted by `streamablehttp_client`/`sse_client`).
- Tests: new unit tests for `_ClientCredentialsAuth.async_auth_flow` (attach / 401-refresh-retry / sticky-unavailable) and `_transport_cm` auth wiring; existing oauth token-resolution tests largely unchanged.
