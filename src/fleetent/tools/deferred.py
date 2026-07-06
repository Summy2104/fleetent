"""Deferred tool loading — pure helpers (deferred-tool-loading).

The agent runtime classifies each LLM-visible tool as **hot** (full schema resident
in `tools=` every turn), **deferred** (only a `name — one-line description` row in a
text catalog), or **activated** (a deferred tool whose schema was fetched this run via
`tool_search` and promoted into `tools=`). These helpers are dependency-free so they
unit-test in isolation; the runtime wiring (loop assembly, catalog injection) lives in
`runtime/loop.py`, and the `tool_search` tool lives in `tools/builtin_tools`.

Naming: helpers operate on the names the model sees (canonical for builtins, the
MCP-projected name for MCP tools — the loop resolves projected→canonical before the
hot decision, so `is_hot_tool` always receives a canonical `{server}__{tool}` name).
"""

import fnmatch
from collections.abc import Callable

from fleetent.tools.registry import ToolSchema

# Canonical MCP tool names join server and tool with this separator (mirrors
# registry._MCP_SEP). A name without it is a builtin tool.
_MCP_SEP = "__"

# Catalog row description cap (single line). Long descriptions are truncated so one
# deferred tool never costs more than a short line in the context window.
_DEFAULT_DESC_MAX = 80

# Default number of keyword hits returned by search_deferred.
_DEFAULT_SEARCH_LIMIT = 10

# select: form prefix — exact tool-name selection, bypassing lexical scoring.
_SELECT_PREFIX = "select:"


def is_hot_tool(canonical_name: str, hot_mcp_servers: list[str]) -> bool:
    """Whether a tool stays hot (full schema resident every turn).

    Builtin tools (no ``__`` separator) are always hot. An MCP tool is hot only when
    its canonical ``{server}__{tool}`` name matches one of the ``hot_mcp_servers``
    fnmatch patterns; with no patterns every MCP tool is deferred.
    """
    if _MCP_SEP not in canonical_name:
        return True
    return any(fnmatch.fnmatch(canonical_name, pattern) for pattern in hot_mcp_servers)


def one_line_desc(schema: ToolSchema, max_len: int = _DEFAULT_DESC_MAX) -> str:
    """First line of a tool schema's description, newline-free and length-capped."""
    raw = schema.get("function", {}).get("description", "") or ""
    first = raw.splitlines()[0].strip() if raw else ""
    if len(first) > max_len:
        first = first[:max_len].rstrip()
    return first


def search_deferred(
    query: str,
    candidates: dict[str, ToolSchema],
    limit: int = _DEFAULT_SEARCH_LIMIT,
) -> list[str]:
    """Resolve a ``tool_search`` query to matching deferred tool names.

    Two forms:
    - ``select:name1,name2`` — exact selection; unknown names are skipped, order kept.
    - free text — case-insensitive token scoring over each candidate's name and
      one-line description (name hits weighted higher); returns the top ``limit`` names.
    """
    if query.startswith(_SELECT_PREFIX):
        wanted = [n.strip() for n in query[len(_SELECT_PREFIX) :].split(",") if n.strip()]
        return [n for n in wanted if n in candidates]

    tokens = [t for t in query.lower().split() if t]
    if not tokens:
        return []
    scored: list[tuple[int, int, str]] = []
    for idx, (name, schema) in enumerate(candidates.items()):
        name_l = name.lower()
        desc_l = one_line_desc(schema).lower()
        score = 0
        for tok in tokens:
            if tok in name_l:
                score += 2
            if tok in desc_l:
                score += 1
        if score > 0:
            # idx as a stable secondary key keeps ordering deterministic for ties.
            scored.append((score, idx, name))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return [name for _score, _idx, name in scored[:limit]]


def _identity(name: str) -> str:
    return name


def partition_schemas(
    schemas: list[ToolSchema],
    hot_mcp_servers: list[str],
    *,
    resolve_canonical: Callable[[str], str] = _identity,
) -> tuple[list[ToolSchema], dict[str, ToolSchema]]:
    """Split already-filtered, model-facing schemas into (hot list, deferred pool).

    ``resolve_canonical`` maps each schema's model-facing name back to its canonical
    name so the hot decision (``is_hot_tool``) sees ``{server}__{tool}`` even when MCP
    name projection is active; it defaults to identity (no projection). The deferred
    pool is keyed by the model-facing name, matching what the catalog and ``tool_search``
    surface to the model.
    """
    hot: list[ToolSchema] = []
    pool: dict[str, ToolSchema] = {}
    for schema in schemas:
        name = schema["function"]["name"]
        if is_hot_tool(resolve_canonical(name), hot_mcp_servers):
            hot.append(schema)
        else:
            pool[name] = schema
    return hot, pool


def assemble_turn_schemas(
    hot_schemas: list[ToolSchema],
    deferred_pool: dict[str, ToolSchema],
    activated: set[str],
) -> list[ToolSchema]:
    """The ``tools=`` array for one turn: hot tools plus any activated deferred tools.

    Activated names absent from the pool (e.g. a tool withdrawn after a list_changed
    refresh) are skipped, so a stale activation can never inject a missing schema.
    """
    return hot_schemas + [deferred_pool[n] for n in activated if n in deferred_pool]


def build_deferred_catalog(
    deferred_pool: dict[str, ToolSchema],
    activated: set[str],
) -> str:
    """Render the deferred-tool catalog text (one ``name — description`` row per tool).

    Tools already in ``activated`` are omitted — they are live in ``tools=`` and need
    no catalog row. Returns an empty string when nothing is deferred.
    """
    rows = [
        f"{name} — {one_line_desc(schema)}" if one_line_desc(schema) else name
        for name, schema in deferred_pool.items()
        if name not in activated
    ]
    return "\n".join(rows)
