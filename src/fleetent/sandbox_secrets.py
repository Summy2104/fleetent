"""Sandbox environment variable filtering and merge pipeline (SB5).

Docker has no native secret primitive, so the env boundary is enforced by a
name-based blacklist: any variable whose name contains a sensitive substring
(case-insensitive) is dropped before reaching a container. Three sources —
host process env, agent-declared `features.sandbox_env`, runtime-supplied — are
merged then filtered at a single point so no source can bypass the rule.

Scope is "clean environment + no-leak": legitimate credentials are intentionally
NOT injected (any normally-named token/key matches the blacklist), and there is
no allowlist exception channel.
"""

from __future__ import annotations

import os

# Sensitive name substrings (case-insensitive). Module-level so tests/extensions
# can monkeypatch it; this is a minimal, extensible set — NOT exhaustive.
SENSITIVE_TOKENS: tuple[str, ...] = (
    "TOKEN",
    "KEY",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "PRIVATE",
    "AUTH",
)


def is_sensitive_name(name: str) -> bool:
    """Return whether `name` contains any sensitive substring (case-insensitive).

    Conservative by design: a benign name embedding a substring (e.g. ``MONKEY``
    contains ``KEY``) is treated as sensitive. The trade-off favours "rather not
    inject than leak".
    """
    upper = name.upper()
    return any(token in upper for token in SENSITIVE_TOKENS)


def build_sandbox_env(
    host_env: dict[str, str] | None = None,
    agent_env: dict[str, str] | None = None,
    runtime_env: dict[str, str] | None = None,
    include_host: bool = False,
) -> dict[str, str]:
    """Merge the three env sources then drop every sensitive-named variable.

    Priority on name collision is host < agent < runtime (later wins). The host
    layer participates only when ``include_host`` is True (it defaults to the
    current process env); otherwise the result starts empty, preserving the
    clean-environment default. Filtering runs once over the merged set so a
    sensitive name from ANY source is removed.

    `runtime_env` exists for pipeline completeness; SB5 wires no caller into it
    (injection is driven solely by agent-declared `features.sandbox_env`).
    """
    merged: dict[str, str] = {}
    if include_host:
        merged.update(host_env if host_env is not None else dict(os.environ))
    if agent_env:
        merged.update(agent_env)
    if runtime_env:
        merged.update(runtime_env)
    return {k: v for k, v in merged.items() if not is_sensitive_name(k)}
