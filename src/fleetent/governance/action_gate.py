"""Action Gate: resolve a tool's risk level to an execution disposition (action-gate).

A pure, side-effect-free mapping from risk level → ``ActionMode`` so the agent loop has
one explicit place to decide direct / sandbox / approval / reject. The two non-negotiable
rules live here, not in the loop:

- CRITICAL is hardcoded REJECT — no config and no LLM-supplied argument can downgrade it.
- Anything we cannot prove safe fails closed (upgrades toward stricter): an unrecognised
  risk string, or a SANDBOX disposition for a tool that is not actually sandbox-backed,
  both become APPROVAL rather than running.

Risk levels come only from the server-side tool registry (``get_risk_level``), never from
LLM-provided arguments — see the loop's call site.
"""

from __future__ import annotations

from enum import StrEnum

# Built-in tools that execute inside the sandbox container (run_code: SB3; the five file
# tools: file-tools-sandbox-execution). For these, a SANDBOX disposition means "already
# structurally isolated, no approval needed". Any tool not listed here cannot satisfy a
# SANDBOX disposition and is failed closed to APPROVAL instead.
SANDBOX_BACKED_TOOLS: frozenset[str] = frozenset(
    {"run_code", "read_file", "write_file", "edit_file", "search_content", "search_files"}
)


class ActionMode(StrEnum):
    DIRECT = "direct"
    SANDBOX = "sandbox"
    APPROVAL = "approval"
    REJECT = "reject"


def is_sandbox_backed(tool_name: str) -> bool:
    """Whether the tool runs inside the sandbox container (so SANDBOX needs no approval)."""
    return tool_name in SANDBOX_BACKED_TOOLS


def _mode_from_str(value: str) -> ActionMode:
    try:
        return ActionMode(value)
    except ValueError:
        # An invalid configured mode is itself "can't prove safe" → fail closed.
        return ActionMode.APPROVAL


def resolve_action_mode(
    risk: str,
    *,
    medium_mode: str,
    high_mode: str,
    sandbox_capable: bool,
    force_ask: bool,
) -> ActionMode:
    """Resolve a tool call's disposition from its risk level and the agent's policy.

    Order matters: CRITICAL is decided first so neither config nor ``force_ask`` can
    relax it; unknown risks fail closed to APPROVAL; ``force_ask`` (a pre_tool_use hook
    asking for confirmation) escalates the rest to APPROVAL; finally a SANDBOX result is
    downgraded to APPROVAL unless the tool is actually sandbox-backed.
    """
    if risk == "critical":
        return ActionMode.REJECT

    if risk in ("none", "low"):
        mode = ActionMode.DIRECT
    elif risk == "medium":
        mode = _mode_from_str(medium_mode)
    elif risk == "high":
        mode = _mode_from_str(high_mode)
    else:
        mode = ActionMode.APPROVAL  # fail closed on an unrecognised risk

    if force_ask:
        mode = ActionMode.APPROVAL

    if mode is ActionMode.SANDBOX and not sandbox_capable:
        mode = ActionMode.APPROVAL  # fail closed: can't guarantee isolation

    return mode
