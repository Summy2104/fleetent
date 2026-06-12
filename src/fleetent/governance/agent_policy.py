"""Per-agent tool-access policy (tool-access-control).

`check_tool_access` is the raw fnmatch predicate for an explicit `allowed_tools`
list. `is_tool_visible` layers the opt-in rule on top so schema assembly and
dispatch share one source of truth for *whether a tool is exposed to this agent*,
including the allow-all (`None`) case.
"""

import fnmatch

# Host-execution tools that MUST NOT be granted implicitly by an empty
# `allowed_tools` (allow-all) or a bare `*` wildcard — an agent must name them
# explicitly to obtain them (sandbox-approval-relaxation). The tool's own
# execution/approval/timeout contract (builtin-shell-tool) is unchanged; only its
# default visibility is.
OPT_IN_TOOLS: frozenset[str] = frozenset({"bash_exec"})


def check_tool_access(tool_name: str, allowed_tools: list[str]) -> bool:
    return any(fnmatch.fnmatch(tool_name, pattern) for pattern in allowed_tools)


def is_tool_visible(tool_name: str, allowed_tools: list[str] | None) -> bool:
    """Whether ``tool_name`` is exposed to an agent with this ``allowed_tools``.

    ``None`` means allow-all (empty `allowed_tools` normalised to ``None``). For
    non-opt-in tools the documented semantics hold: allow-all exposes everything,
    an explicit list keeps only fnmatch-matching tools. An opt-in tool
    (``OPT_IN_TOOLS``) is exposed ONLY when an explicit, non-bare-``*`` pattern in
    ``allowed_tools`` matches it; allow-all (``None``) and a bare ``["*"]`` never
    grant it.
    """
    if tool_name in OPT_IN_TOOLS:
        if allowed_tools is None:
            return False
        explicit = [p for p in allowed_tools if p != "*"]
        return check_tool_access(tool_name, explicit)
    if allowed_tools is None:
        return True
    return check_tool_access(tool_name, allowed_tools)
