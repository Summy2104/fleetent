## Why

`mcp-sdk-oauth` implemented oauth2 client_credentials as a fleetent-owned `httpx.Auth` (`_ClientCredentialsAuth`) that hand-rolls the token POST. The official SDK actually ships a maintained provider for this exact grant — `mcp.client.auth.extensions.client_credentials.ClientCredentialsOAuthProvider` — which also brings standards features fleetent's hand-rolled path lacks: RFC 8707 resource (audience) binding, multiple client-auth methods (basic/post), WWW-Authenticate-driven scope/AS handling, and SDK-maintained token lifecycle. This change adopts the SDK provider so the OAuth client logic is maintained upstream and gains those features, while keeping fleetent's explicit `token_url` config model (no forced discovery).

See `decisions.md` for the verified findings that shaped this (the SDK provider's reactive 401-driven flow, mandatory `.well-known` probing, and how preseeding reconciles the explicit `token_url`).

## What Changes

- Add `_FleetentClientCredentialsProvider(ClientCredentialsOAuthProvider)`: a thin subclass that (a) maps fleetent's `McpServerConfig` (`url`/`client_id`/`client_secret_env`/`scope`/`token_url`) onto the SDK provider, (b) **preseeds** `context.oauth_metadata` from the explicit `token_url` so the token endpoint works without requiring the server to expose `.well-known` discovery, and (c) overrides `_handle_token_response` to preserve fleetent's **genuine-vs-transient** distinction (bad credentials → sticky auth-unavailable; 5xx/network → retryable).
- Add `_FleetentTokenStorage(TokenStorage)`: a minimal in-memory token store satisfying the SDK's storage protocol, isolated per provider/session.
- `_oauth_auth(server)` returns the SDK-backed provider for `oauth2` (was: `_ClientCredentialsAuth`); api_key / none / stdio unchanged (`auth=None`).
- `_call_via_session` / `_call_utility`: map the SDK's OAuth errors onto fleetent's existing degraded-result contract — genuine auth failure (sticky flag side effect) → "authentication unavailable" text; transient OAuth/token errors → degraded but not sticky (never crash the agent loop).
- **REMOVE** the hand-rolled A machinery now superseded by the SDK provider: `_ClientCredentialsAuth`, `_resolve_oauth_token`, `_fetch_client_credentials_token`, `_token_is_valid`, `_is_auth_error_response`, `_is_transient_token_error`, fleetent's `OAuthToken` / `_InMemoryTokenStore`, and the now-unused `_token_store` / `_refresh_lock` fields + TTL constants. Keep `_auth_unavailable` (sticky flag) and `_clear_oauth_auth_state` (recovery on re-registration).

Non-goals: no authorization_code/PKCE, no private_key_jwt (the SDK's `PrivateKeyJWTOAuthProvider` is available later if needed), no change to api_key/stdio paths.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `mcp-oauth2-auth`: the oauth2 client_credentials flow is now performed by the official SDK provider (token acquisition, TTL/refresh, RFC 8707 resource binding, client-auth method) injected via the transport `auth=`, instead of a fleetent hand-rolled token POST. fleetent keeps the explicit `token_url` (preseeded as the SDK's token endpoint, discovery used only if the server exposes it) and preserves the sticky auth-unavailable + transient-retryable semantics via a subclass override.

## Impact

- Code: `src/fleetent/integrations/mcp/client.py` (new provider subclass + token storage; `_oauth_auth` rewired; A's token machinery removed; call-path error mapping updated). `pyproject.toml` already depends on `mcp`; the provider lives in `mcp.client.auth.extensions` (no new dependency).
- Behavior change (documented in `decisions.md`): the SDK provider is **reactive** — the first request of a fresh session goes out without a token and authenticates on the 401 challenge, and the SDK probes `.well-known` on 401. fleetent's prior A attached the token proactively. This requires the MCP server to issue a 401 (ideally with `WWW-Authenticate`) and to return 404 (not 401) for absent `.well-known`.
- No oauth2 server exists in the current my-bot deployment, so this path is exercised by tests (httpx `MockTransport` simulating the full 401 → discovery → token → retry sequence), not by a live server.
