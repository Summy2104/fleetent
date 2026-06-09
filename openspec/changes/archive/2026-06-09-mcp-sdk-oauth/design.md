## Context

`mcp-sdk-transport` unified all transports onto a held SDK `ClientSession` with the bearer resolved once at session-open (`_http_headers` → transport `headers=`). For `oauth2` `client_credentials` servers this regressed per-request token freshness: a long-lived session keeps a baked token, and a mid-session `401` (an `httpx.HTTPStatusError`) is not a disconnect, so neither lazy-reconnect nor any refresh recovers it.

The SDK's `OAuthClientProvider` only does `authorization_code`+PKCE (+`refresh_token`); it requires interactive redirect/callback handlers and cannot perform `client_credentials`. The SDK transports (`streamablehttp_client`/`sse_client`) accept any `httpx.Auth` via `auth=`, and the SDK uses an `httpx.AsyncClient`, so a custom `httpx.Auth` overriding `async_auth_flow` runs per-request — the idiomatic injection point.

## Goals / Non-Goals

**Goals:**
- Inject the `oauth2` bearer per-request via the SDK transport `auth=`, restoring token freshness on the held session.
- Refresh + retry once on a mid-session `401` without reopening the session.
- Reuse the existing token fetch / cache / refresh-lock / sticky-`_auth_unavailable` machinery unchanged.

**Non-Goals:**
- No `authorization_code`/PKCE, no `OAuthClientProvider`.
- No change to `api_key` / `none` / stdio auth paths.
- No change to token-cache isolation or sticky-unavailable recovery semantics (config reload / re-registration).
- Not replacing the hand-written `client_credentials` token POST — the SDK has no such grant.

## Decisions

- **`_ClientCredentialsAuth(httpx.Auth)`** wraps a server config and overrides `async_auth_flow(request)`:
  1. `token = await _resolve_oauth_token(server)` (cache hit returns immediately; miss/expiry fetches via the existing path), set `Authorization: Bearer <token>`.
  2. `response = yield request`.
  3. If `response.status_code == 401`: `server._token_store.clear(server.id)`, re-resolve, re-attach, `yield request` once more (single retry).
  It is a thin adapter — all token logic stays in `_resolve_oauth_token` / `_fetch_client_credentials_token`.
- **Injection point:** `_transport_cm` passes `auth=_ClientCredentialsAuth(server)` for `oauth2` http/sse; `None` otherwise. A small `_oauth_auth(server)` helper returns the auth or `None`.
- **`_http_headers`** drops the oauth bearer branch; keeps custom `env:`-resolved headers + static `api_key` bearer. (api_key is a static env value — no refresh needed, `headers=` is correct for it.)
- **Genuine auth failure:** `_fetch_client_credentials_token` still raises `OAuthAuthUnavailableError` and sets sticky `_auth_unavailable`. That exception propagates out of `session.call_tool`/`initialize`; `_call_via_session` (and `_call_utility`) catch `OAuthAuthUnavailableError` and return the existing "authentication unavailable" degraded text. The upfront `_auth_unavailable` check short-circuits subsequent calls (unchanged). Recovery via `_clear_oauth_auth_state` on re-registration (unchanged).
- **Initialize handshake** also flows through the transport's `auth=`, so the token is attached on `initialize` too — uniform, no special-casing.

## Risks / Trade-offs

- **Token POST stays hand-rolled.** Acceptable and unavoidable: the SDK offers no `client_credentials` grant. It is small, already tested, and reused as-is.
- **401 semantics depend on the server.** The retry triggers only on a real HTTP 401 surfaced to the auth flow. A server that signals expiry differently (e.g. a JSON-RPC error body with 200) would not trigger the auth-flow retry — but that already falls under normal call-error handling, and `client_credentials` expiry conventionally returns 401. Documented, not engineered around (YAGNI).
- **Double `yield` contract.** `httpx.Auth.async_auth_flow` must `yield` at most twice and not consume the response stream incorrectly; the implementation yields the same `request` object, matching httpx's documented retry pattern.
