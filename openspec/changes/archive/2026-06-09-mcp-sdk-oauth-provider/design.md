## Context

`mcp-sdk-oauth` injects oauth2 via a fleetent `httpx.Auth` (`_ClientCredentialsAuth`) that hand-rolls the client_credentials POST and reuses fleetent's per-server token cache + sticky `_auth_unavailable`. The SDK ships `ClientCredentialsOAuthProvider` (a subclass of `OAuthClientProvider`, itself an `httpx.Auth`) that performs the same grant with maintained token lifecycle + RFC 8707. This change swaps fleetent's hand-rolled auth for the SDK provider, adapted to fleetent's explicit `token_url` config. The verified SDK behavior and every decision/trade-off are recorded in `decisions.md` (read it alongside this).

## Goals / Non-Goals

**Goals:**
- Perform oauth2 client_credentials via the official SDK provider, injected through the transport `auth=`.
- Keep fleetent's explicit `token_url` config working without requiring server-side `.well-known` discovery (preseed).
- Preserve the spec's sticky-auth-unavailable (bad creds) vs transient-retryable (5xx/network) semantics, and the degraded-result-never-crash contract.

**Non-Goals:**
- authorization_code/PKCE, private_key_jwt (PrivateKeyJWTOAuthProvider available later).
- Changing api_key / none / stdio auth.
- Reimplementing the SDK's auth flow to make it proactive (that would just recreate A).

## Decisions

(Full rationale in `decisions.md` D1–D7, R1–R3. Summary:)

- **Adopt the SDK provider via a thin subclass** `_FleetentClientCredentialsProvider(ClientCredentialsOAuthProvider)`:
  - map config → provider (`server_url=url`, `client_id`, `client_secret` from `client_secret_env`, `scopes=scope`, `token_endpoint_auth_method="client_secret_post"`);
  - **preseed** `context.oauth_metadata` from `token_url` in `_initialize` (D2) so the explicit token endpoint is used without discovery;
  - override `_handle_token_response` to split genuine (sticky) vs transient (retryable) (D4) — set `server._auth_unavailable` + raise `OAuthAuthUnavailableError` on invalid_client/invalid_grant; delegate to super otherwise.
- **`_FleetentTokenStorage`** — minimal in-memory `TokenStorage` (D6), per provider/session.
- **`_oauth_auth(server)`** returns the SDK provider for oauth2; None otherwise (unchanged for api_key/stdio).
- **Call-path mapping** (D5): catch on the sticky side-effect first (robust to exception wrapping), then transient SDK OAuth errors → degraded (no crash), then disconnect → lazy reconnect.
- **Remove** A's token machinery (`_ClientCredentialsAuth`, `_resolve_oauth_token`, `_fetch_client_credentials_token`, `_token_is_valid`, `_is_auth_error_response`, `_is_transient_token_error`, fleetent `OAuthToken`, `_InMemoryTokenStore`, `_token_store`/`_refresh_lock` fields, TTL consts). Keep `_auth_unavailable`, `_clear_oauth_auth_state`, `OAuthAuthUnavailableError` (now the sticky signal raised by the override).

## Risks / Trade-offs

- **Reactive 401 flow** (D1): tokenless first request + 401 dependence + discovery chatter. Heavier and more server-dependent than A.
- **Bare-server incompatibility** (R1): a server that 401s `.well-known` (instead of 404) breaks the SDK's discovery probe. B requires reasonably spec-compliant servers.
- **No live oauth2 server** (R2): validated via httpx `MockTransport` simulating the full sequence, not a real server.
- **SDK-internal coupling** (R3): preseed + `_handle_token_response` override depend on SDK internals; MCP unit suite catches drift.
- Reversible: the swap is localized to `_oauth_auth` + the removed A code; revert = revert the PR.
