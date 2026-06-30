"""Minimal per-user api-key MCP server for local testing of `auth_type=api_key_per_user`.

Unlike scripts/mock_mcp_server.py (a simplified raw JSON-RPC echo), this speaks the real
streamable-http MCP protocol via the official SDK (FastMCP), so fleetent's actual MCP client
connects to it end-to-end. It requires a per-user api-key on every request and rejects a
missing/unknown key with 401 — which is exactly what drives fleetent's "needs credential"
degrade + submission flow.

Auth header is chosen by the SERVER (matching the agent.yaml `header_style`):
  - `Authorization: Bearer <key>`   (header_style=bearer, the default)
  - `X-API-Key: <key>`              (header_style=x_api_key)
This stub accepts either, so the same server works for both header styles.

Configure the agent (agent.yaml)::

    mcp_servers:
      - id: apikey-demo
        transport: http
        url: http://127.0.0.1:9000/mcp
        auth_type: api_key_per_user
        header_style: bearer        # or x_api_key
        credential_input: both      # form + tool (form=only form, tool=only tool)

Run::

    uv run python scripts/mock_mcp_apikey_server.py            # port 9000
    PORT=9100 KEYS=alice=Alice,bob=Bob \
        uv run python scripts/mock_mcp_apikey_server.py        # custom port + keys
"""

from __future__ import annotations

import contextvars
import os

from mcp.server.fastmcp import FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request


def _load_keys() -> dict[str, str]:
    """Valid key -> display identity. Override via env ``KEYS=key1=Name1,key2=Name2``."""
    raw = os.environ.get("KEYS", "alice-key-123=Alice,bob-key-456=Bob")
    keys: dict[str, str] = {}
    for pair in raw.split(","):
        if "=" in pair:
            key, name = pair.split("=", 1)
            keys[key.strip()] = name.strip()
    return keys


VALID_KEYS = _load_keys()

# The identity the presented key authenticated as for the current request (None = no/invalid
# key). Tool calls require it; discovery leaves it unset and still succeeds.
_who: contextvars.ContextVar[str | None] = contextvars.ContextVar("who", default=None)

# stateless_http: each request is self-contained (simplest to reason about for a stub).
# json_response: respond with plain JSON (no forced SSE), so `curl` can probe it too.
mcp = FastMCP("apikey-stub", stateless_http=True, json_response=True)


def _require_identity() -> str:
    """Return the authenticated identity, or raise so the tool call fails without a key.

    Tool CALLS require a valid per-user key; discovery (initialize / tools/list) does not run
    tools, so the catalog stays visible to clients that have not supplied a key yet.
    """
    who = _who.get()
    if who is None:
        raise ValueError("missing or invalid api key — provide your per-user credential")
    return who


@mcp.tool()
def whoami() -> str:
    """Return which user the presented api-key authenticates as.

    Different keys resolve to different identities, so two users calling with their own keys
    see their own identity — a visible demonstration of per-user isolation.
    """
    return f"authenticated as: {_require_identity()}"


@mcp.tool()
def echo(text: str) -> str:
    """Echo the text back, tagged with the authenticated identity."""
    return f"[{_require_identity()}] {text}"


class ApiKeyAuth(BaseHTTPMiddleware):
    """Resolve the per-user key from the request header into a context var.

    Reads only the header (never the body) so it never interferes with the MCP
    streamable-http stream. It does NOT reject: discovery (initialize / tools/list) must stay
    open so the agent can register the tool catalog at boot — the per-user model authenticates
    on the tool CALL, which the tools enforce via :func:`_require_identity`. A request with no
    valid key leaves the identity unset (tool calls then fail; discovery still works).
    """

    async def dispatch(self, request: Request, call_next):  # type: ignore[no-untyped-def]
        auth = request.headers.get("authorization", "")
        key = (
            auth[len("Bearer ") :]
            if auth.startswith("Bearer ")
            else request.headers.get("x-api-key")
        )
        token = _who.set(VALID_KEYS.get(key or ""))
        try:
            return await call_next(request)
        finally:
            _who.reset(token)


app = mcp.streamable_http_app()
app.add_middleware(ApiKeyAuth)


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "9000"))
    print(f"Mock per-user api-key MCP server on http://127.0.0.1:{port}/mcp")
    print(f"Valid keys: {', '.join(f'{k}->{v}' for k, v in VALID_KEYS.items())}")
    uvicorn.run(app, host="127.0.0.1", port=port)
