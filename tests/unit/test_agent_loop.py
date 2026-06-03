"""Unit tests for agent_loop binding resolution (skills allowlist + MCP union).

Pure helpers are tested with monkeypatched stores so no DB/LLM is touched.
"""

from pathlib import Path

import fleetent.agent_loop as al
from fleetent.agent_runtime import AgentSnapshot


def _snapshot(**over: object) -> AgentSnapshot:
    base: dict[str, object] = {
        "agent_id": 7,
        "name": "ops",
        "version": 1,
        "version_id": 1,
        "system_prompt": "You are ops.",
        "allowed_tools": [],
        "skills_dir": None,
        "mcp_server_ids": None,
        "model_overrides": {},
        "memory_namespace": "default",
    }
    base.update(over)
    return AgentSnapshot(**base)  # type: ignore[arg-type]


# --- skill allowlist ----------------------------------------------------------


def test_resolve_skill_allowlist_none_snapshot():
    assert al._resolve_skill_allowlist(None) is None


def test_resolve_skill_allowlist_no_bindings_returns_none(monkeypatch):
    monkeypatch.setattr(al.skill_admin_store, "has_any_binding", lambda name: False)
    assert al._resolve_skill_allowlist(_snapshot()) is None


def test_resolve_skill_allowlist_enabled_subset(monkeypatch):
    monkeypatch.setattr(al.skill_admin_store, "has_any_binding", lambda name: True)
    monkeypatch.setattr(al.skill_admin_store, "enabled_skill_names", lambda name: {"alpha"})
    assert al._resolve_skill_allowlist(_snapshot()) == {"alpha"}


# --- MCP union ----------------------------------------------------------------


def test_resolve_mcp_ids_none_snapshot():
    assert al._resolve_mcp_ids(None) is None


def test_resolve_mcp_ids_base_none_no_bindings_stays_none(monkeypatch):
    monkeypatch.setattr(al.agent_store, "list_mcp_servers_for_agent", lambda aid: [])
    assert al._resolve_mcp_ids(_snapshot(mcp_server_ids=None)) is None


def test_resolve_mcp_ids_base_none_with_bindings(monkeypatch):
    monkeypatch.setattr(al.agent_store, "list_mcp_servers_for_agent", lambda aid: ["github"])
    assert al._resolve_mcp_ids(_snapshot(mcp_server_ids=None)) == ["github"]


def test_resolve_mcp_ids_union(monkeypatch):
    monkeypatch.setattr(al.agent_store, "list_mcp_servers_for_agent", lambda aid: ["jira"])
    out = al._resolve_mcp_ids(_snapshot(mcp_server_ids=["github"]))
    assert out == ["github", "jira"]


# --- skill matching honours the allowlist -------------------------------------


def _write_skill(base: Path, name: str, description: str) -> None:
    d = base / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(f"---\nname: {name}\ndescription: {description}\n---\nBody {name}.")


def test_match_skill_for_filtered_by_allowlist(tmp_path, monkeypatch):
    _write_skill(tmp_path, "alpha", "Use when provisioning compute clusters.")
    monkeypatch.setattr(al.skill_admin_store, "has_any_binding", lambda name: True)
    monkeypatch.setattr(al.skill_admin_store, "enabled_skill_names", lambda name: set())
    snap = _snapshot(skills_dir=str(tmp_path))
    # alpha exists on disk but is not enabled → must not match
    assert al._match_skill_for("help me provisioning a cluster", snap) is None


def test_match_skill_for_allows_when_enabled(tmp_path, monkeypatch):
    _write_skill(tmp_path, "alpha", "Use when provisioning compute clusters.")
    monkeypatch.setattr(al.skill_admin_store, "has_any_binding", lambda name: True)
    monkeypatch.setattr(al.skill_admin_store, "enabled_skill_names", lambda name: {"alpha"})
    snap = _snapshot(skills_dir=str(tmp_path))
    assert "Body alpha." in (al._match_skill_for("help me provisioning a cluster", snap) or "")
