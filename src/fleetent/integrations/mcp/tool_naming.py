"""MCP tool-name projection engine (mcp-tool-name-projection).

Renders an MCP tool's model-facing name from its canonical ``(server_id, raw_tool)``
identity through a configurable projection (a preset alias or a custom template). The
projection is declarative so supporting a new platform's naming convention is a config
change, not a code branch.

This module is pure and stateless: it ONLY renders names. The agent-process-local
reverse-lookup table that resolves an inbound projected name back to its canonical
identity is the caller's responsibility (``client.py`` builds it at registration),
because projected names — especially single-underscore presets like ``hermes`` —
cannot be safely round-tripped by string splitting. Keeping render and resolve apart
is what lets governance bind the canonical identity regardless of the projection.

Agent-side only: never imports the platform control-plane. The config type is duck-typed
(any object exposing ``template`` / ``sanitize`` / ``max_len``) to avoid coupling to
``fleetent.config.McpToolNamingTemplate``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

# Preset alias → projection template. The default `claude` (`mcp__{server}__{tool}`) is
# the most-authoritative convention: the double underscore makes the server/tool boundary
# unambiguous. Single-underscore presets (hermes/opencode) are ambiguous on the wire and
# rely on the caller's reverse-lookup table, never on re-parsing the projected name.
_PRESET_TEMPLATES: dict[str, str] = {
    "claude": "mcp__{server}__{tool}",
    "hermes": "mcp_{server}_{tool}",
    "opencode": "{server}_{tool}",
    "skills": "{server}:{tool}",
    "bare": "{server}__{tool}",
}

# Preset alias used when `tool_naming` is empty/unset.
_DEFAULT_PRESET = "claude"

# Default cap on a projected name's length (the LLM tool-name limit fleetent targets).
_DEFAULT_MAX_LEN = 64

# `snake` policy: collapse every character outside the safe identifier set to `_`.
_UNSAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9_]")

# Hex width of the disambiguating hash suffix appended when a name is over `max_len`.
_HASH_SUFFIX_LEN = 8


@dataclass(frozen=True)
class Projector:
    """Renders canonical ``(server_id, raw_tool)`` pairs into model-facing tool names.

    Immutable and stateless so a single instance can be reused for every tool of an
    agent without hidden coupling between calls. Construct via :func:`make_projector`.

    Attributes:
        template: Render template using ``{server}`` and ``{tool}`` placeholders.
        sanitize: Character policy applied to each part before substitution
            (``"none"`` = passthrough, ``"snake"`` = non-``[A-Za-z0-9_]`` → ``_``).
        max_len: Maximum length of the rendered name; longer names are deterministically
            shortened while staying unique for distinct inputs.
    """

    template: str
    sanitize: str
    max_len: int

    def project(self, server_id: str, raw_tool: str) -> str:
        """Render the model-facing name for one MCP tool.

        Args:
            server_id: Canonical MCP server id.
            raw_tool: Server-local tool name as advertised by the server.

        Returns:
            The projected, length-capped tool name to expose to the model.
        """
        server = _apply_sanitize(server_id, self.sanitize)
        tool = _apply_sanitize(raw_tool, self.sanitize)
        rendered = self.template.format(server=server, tool=tool)
        return _enforce_max_len(rendered, self.max_len)


def make_projector(tool_naming: object) -> Projector:
    """Build a :class:`Projector` from an ``mcp.tool_naming`` value.

    Accepts a preset alias string (``claude`` / ``hermes`` / ``opencode`` / ``skills`` /
    ``bare``), a custom template object exposing ``template`` / ``sanitize`` / ``max_len``
    (e.g. ``config.McpToolNamingTemplate``), or an equivalent mapping. An empty or
    ``None`` value defaults to the ``claude`` preset.

    Args:
        tool_naming: The configured projection: preset string, template object, or dict.

    Returns:
        A stateless projector rendering canonical pairs into model-facing names.

    Raises:
        ValueError: If ``tool_naming`` is an unknown preset string, or an object/mapping
            missing a ``template``.
    """
    # Empty/unset → most-authoritative default rather than an error: the field is
    # optional in agent.yaml and a blank value is a legitimate "use the default".
    if tool_naming is None or tool_naming == "":
        return _preset_projector(_DEFAULT_PRESET)

    if isinstance(tool_naming, str):
        return _preset_projector(tool_naming)

    template, sanitize, max_len = _read_template_attrs(tool_naming)
    return Projector(template=template, sanitize=sanitize, max_len=max_len)


def _preset_projector(preset: str) -> Projector:
    """Resolve a preset alias to its built-in template (presets use ``none``/64)."""
    try:
        template = _PRESET_TEMPLATES[preset]
    except KeyError:
        valid = ", ".join(sorted(_PRESET_TEMPLATES))
        raise ValueError(
            f"Unknown MCP tool_naming preset {preset!r}; expected one of: {valid}, "
            "or a custom template object."
        ) from None
    return Projector(template=template, sanitize="none", max_len=_DEFAULT_MAX_LEN)


def _read_template_attrs(tool_naming: object) -> tuple[str, str, int]:
    """Duck-type a custom template's ``template`` / ``sanitize`` / ``max_len``.

    Supports both attribute objects (``McpToolNamingTemplate``) and plain mappings so the
    engine stays decoupled from the config model.
    """
    if isinstance(tool_naming, dict):
        if "template" not in tool_naming:
            raise ValueError("Custom MCP tool_naming mapping must define 'template'.")
        template = tool_naming["template"]
        sanitize = tool_naming.get("sanitize", "none")
        max_len = tool_naming.get("max_len", _DEFAULT_MAX_LEN)
    else:
        template = getattr(tool_naming, "template", None)
        if template is None:
            raise ValueError(
                "Custom MCP tool_naming must be a preset string or expose a 'template' "
                f"attribute; got {type(tool_naming).__name__}."
            )
        sanitize = getattr(tool_naming, "sanitize", "none")
        max_len = getattr(tool_naming, "max_len", _DEFAULT_MAX_LEN)
    return str(template), str(sanitize), int(max_len)


def _apply_sanitize(part: str, sanitize: str) -> str:
    """Apply the configured character policy to one name part before substitution."""
    if sanitize == "snake":
        return _UNSAFE_CHARS_RE.sub("_", part)
    # Default `none`: passthrough. Unknown policies are treated as passthrough so a
    # typo degrades to the canonical text rather than crashing tool registration.
    return part


def _enforce_max_len(rendered: str, max_len: int) -> str:
    """Cap ``rendered`` at ``max_len``, staying deterministic and collision-free.

    Names within the limit are returned verbatim. Over-limit names are truncated and get
    an 8-hex-char sha256 suffix of the FULL rendered name, so two distinct inputs that
    share a truncated prefix still differ in the suffix.
    """
    if len(rendered) <= max_len:
        return rendered
    suffix = hashlib.sha256(rendered.encode()).hexdigest()[:_HASH_SUFFIX_LEN]
    # Reserve room for the suffix; `max(0, ...)` guards pathologically tiny max_len.
    head_len = max(0, max_len - len(suffix))
    return rendered[:head_len] + suffix
