"""Central approval policy — the single authority for "does this tool call need approval".

The principle (approval-boundary-redesign) is the **recipient-identity axis**: a call needs
approval (``medium``) iff the agent proactively delivers content to a recipient *other than the
current conversation participant* (a DM to someone else, a post to a different channel, an
email). Replying to the current conversation, local work, and sandboxed execution do not.

`risk_for` is the one entry point: `runtime/loop.py` dispatch and `tools/registry`'s
`evaluate_risk_level` both route through it. It never lowers a band from LLM-supplied args
(anti-escape) and fails closed to ``medium`` on any unexpected error. Tools it does not
specially classify return their registered static risk via the ``fallback`` argument — so
``run_code`` keeps its static ``medium`` and remains governed by `sandbox-containment-gating`,
which this policy deliberately does not override.

This module MUST NOT import `fleetent.tools.*` (the dependency runs tools→governance; the
reverse would cycle): callers pass the registered static band in as ``fallback``.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Per-server MCP approval rules loaded from agent.yaml at MCP registration (D4). Maps
# server_id -> list of {"tool": str, "when": {arg: [allowed, ...]} | None}. A configured
# entry overrides the built-in default for that server.
_mcp_rules: dict[str, list[dict[str, Any]]] = {}

# Built-in defaults shipped for well-known servers (D4): applied only when the agent did not
# configure approval_rules for that server. google-workspace email send/reply/forward is gated
# by default so the MCP zero-approval hole is closed out of the box.
_BUILTIN_MCP_RULES: dict[str, list[dict[str, Any]]] = {
    "google-workspace": [
        {"tool": "manage_email", "when": {"operation": ["send", "reply", "replyAll", "forward"]}},
    ],
}


def reset_mcp_rules() -> None:
    """Clear all configured MCP rules (test isolation / re-registration)."""
    _mcp_rules.clear()


def set_server_mcp_rules(server_id: str, rules: list[Any]) -> None:
    """Upsert one server's approval rules (MCP registration; does not clear other servers).

    Rules may be plain dicts or pydantic ``McpApprovalRule`` (duck-typed via ``model_dump``).
    Empty rules removes the server's override so its built-in default (if any) applies.
    """
    normalized = [r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rules]
    if normalized:
        _mcp_rules[server_id] = normalized
    else:
        _mcp_rules.pop(server_id, None)


def set_agent_mcp_rules(rules_by_server: dict[str, list[Any]]) -> None:
    """Install per-server approval rules parsed from agent.yaml (replaces prior state).

    Each rule may be a plain dict or a pydantic ``McpApprovalRule`` (duck-typed via
    ``model_dump`` so this module needs no config import); both normalize to dicts.
    """
    _mcp_rules.clear()
    for server_id, rules in rules_by_server.items():
        _mcp_rules[server_id] = [
            r.model_dump() if hasattr(r, "model_dump") else dict(r) for r in rules
        ]


def risk_for(name: str, args: dict[str, Any], tool_context: Any, *, fallback: str = "none") -> str:
    """Resolve a tool call's risk band on the recipient-identity axis.

    ``fallback`` is the tool's registered static band (passed by the caller, which owns the
    tools registry). Tools this policy does not specially classify return ``fallback``
    unchanged. Any unexpected error fails closed to ``medium`` — a buggy policy must never
    silently drop a call below the approval threshold.
    """
    try:
        return _classify(name, args if isinstance(args, dict) else {}, tool_context, fallback)
    except Exception:  # noqa: BLE001 — fail closed: policy errors must not bypass the gate
        logger.warning("approval_policy_failed name=%s", name)
        return "medium"


def _classify(name: str, args: dict[str, Any], ctx: Any, fallback: str) -> str:
    # Anti-escape is structural: this function never reads a "risk"/"risk_level" field
    # out of args; bands derive only from system facts (the tool + recipient + rules).
    if name == "send_im_message":
        return _send_im_risk(args, ctx)
    if name == "send_file":
        # No recipient parameter — always replies to the current conversation, so it is never
        # proactive outreach to someone else. Cross-scope artifact safety is a separate hard
        # guard in the /exchange resolver, not an approval concern.
        return "none"
    if name == "invoke_agent":
        # Dispatching to a sub-agent is not outreach to a recipient; the sub-agent's own
        # outbound actions remain individually gated when it runs.
        return "none"
    if "__" in name:
        return _mcp_risk(name, args)
    return fallback


def _mcp_risk(name: str, args: dict[str, Any]) -> str:
    """MCP tool (``{server}__{tool}``) on the approval-rules table: ``medium`` if a rule
    matches, else ``none`` (the narrow-surface default). Configured rules override the
    built-in defaults for that server."""
    server_id, _, local_tool = name.partition("__")
    rules = _mcp_rules.get(server_id)
    if rules is None:
        rules = _BUILTIN_MCP_RULES.get(server_id, [])
    for rule in rules:
        if rule.get("tool") != local_tool:
            continue
        when = rule.get("when")
        if when is None:
            return "medium"  # whole-tool rule
        if all(str(args.get(arg)) in [str(v) for v in allowed] for arg, allowed in when.items()):
            return "medium"
    return "none"


def _send_im_risk(args: dict[str, Any], ctx: Any) -> str:
    """send_im_message on the recipient-identity axis: ``none`` iff the target resolves to
    the current conversation (same DM user or same channel), else ``medium``. No resolvable
    current-conversation address → fail closed to ``medium``."""
    sc = getattr(ctx, "session_context", None)
    if sc is None:
        return "medium"
    target = str(args.get("target") or "")
    target_type = str(args.get("target_type") or "user")
    if not target:
        return "medium"
    if target_type == "user":
        same = target == str(getattr(sc, "sender_id", "") or "")
    elif target_type == "channel":
        same = target == str(getattr(sc, "channel_name", "") or "")
    else:
        same = False
    return "none" if same else "medium"
