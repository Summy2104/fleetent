"""Unit tests for the MCP tool-name projection engine (mcp-tool-name-projection).

Pure/stateless render-only behavior: preset aliases, custom templates, the `snake`
sanitize policy, and deterministic length-capped shortening. The reverse-lookup table
is the caller's job, so it is intentionally out of scope here.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

import pytest

from fleetent.integrations.mcp.tool_naming import make_projector


@dataclass
class _NamingStub:
    """Duck-typed stand-in for ``config.McpToolNamingTemplate`` (no pydantic import)."""

    template: str
    sanitize: str = "none"
    max_len: int = 64


@pytest.mark.parametrize(
    ("preset", "expected"),
    [
        ("claude", "mcp__github__create_issue"),
        ("hermes", "mcp_github_create_issue"),
        ("opencode", "github_create_issue"),
        ("skills", "github:create_issue"),
        ("bare", "github__create_issue"),
    ],
)
def test_preset_projection(preset: str, expected: str) -> None:
    projector = make_projector(preset)
    assert projector.project("github", "create_issue") == expected


def test_default_is_claude_when_empty() -> None:
    # An empty/unset value must fall back to the most-authoritative `claude` preset.
    for empty in ("", None):
        projector = make_projector(empty)
        assert projector.project("github", "create_issue") == "mcp__github__create_issue"


def test_custom_template_object() -> None:
    projector = make_projector(_NamingStub(template="{server}:{tool}"))
    assert projector.project("github", "create_issue") == "github:create_issue"


def test_custom_template_dict() -> None:
    projector = make_projector({"template": "{server}.{tool}"})
    assert projector.project("github", "create_issue") == "github.create_issue"


def test_sanitize_snake_replaces_unsafe_chars() -> None:
    # google-drive → google_drive; the dot in the tool likewise becomes an underscore.
    projector = make_projector(_NamingStub(template="{server}_{tool}", sanitize="snake"))
    assert projector.project("google-drive", "list.files") == "google_drive_list_files"


def test_sanitize_none_is_default() -> None:
    # Without snake, unsafe characters pass through untouched.
    projector = make_projector(_NamingStub(template="{server}_{tool}"))
    assert projector.project("google-drive", "list.files") == "google-drive_list.files"


def test_unknown_preset_raises_value_error() -> None:
    with pytest.raises(ValueError):
        make_projector("definitely-not-a-preset")


def test_max_len_caps_long_names() -> None:
    server = "s" * 50
    tool = "t" * 50
    projector = make_projector(_NamingStub(template="{server}__{tool}", max_len=64))
    projected = projector.project(server, tool)
    assert len(projected) <= 64


def test_max_len_keeps_distinct_inputs_distinct() -> None:
    server = "s" * 50
    projector = make_projector(_NamingStub(template="{server}__{tool}", max_len=64))
    a = projector.project(server, "t" * 50 + "A")
    b = projector.project(server, "t" * 50 + "B")
    assert a != b
    assert len(a) <= 64 and len(b) <= 64


def test_max_len_shortening_is_deterministic_and_hash_suffixed() -> None:
    # The shortened name appends the first 8 hex chars of the full rendered name's
    # sha256 so distinct inputs cannot collide; verify that exact suffix is used.
    server = "x" * 60
    tool = "y" * 60
    projector = make_projector(_NamingStub(template="{server}__{tool}", max_len=64))
    full = f"{server}__{tool}"
    expected_suffix = hashlib.sha256(full.encode()).hexdigest()[:8]
    projected = projector.project(server, tool)
    assert projected == projector.project(server, tool)  # deterministic
    assert projected.endswith(expected_suffix)
    assert len(projected) <= 64


def test_short_name_unchanged_by_max_len() -> None:
    # Names already within the cap must be returned verbatim (no hashing).
    projector = make_projector("claude")
    assert projector.project("gh", "ping") == "mcp__gh__ping"


def test_projector_is_stateless_and_reusable() -> None:
    # Repeated, interleaved calls on one projector return stable results (no hidden state).
    projector = make_projector("hermes")
    assert projector.project("a", "b") == "mcp_a_b"
    assert projector.project("c", "d") == "mcp_c_d"
    assert projector.project("a", "b") == "mcp_a_b"
