"""Unit tests for the file-driven agent config loader (file-agent-runtime)."""

import pytest
import yaml
from pydantic import ValidationError

from fleetent import agent_config


def _valid_doc() -> dict:
    return {
        "name": "support",
        "version": 7,
        "tenant_id": "acme",
        "team_id": "t1",
        "system_prompt": "You are support.",
        "model_overrides": {"default": {"model": "claude-opus-4-8"}},
        "memory_namespace": "support",
        "skills_dir": "skills",
        "allowed_skills": ["triage"],
        "allowed_tools": ["search_*", "acme__*"],
        "plugins": ["acme"],
        "features": {"code_execution": True},
        "mcp_servers": [
            {
                "id": "acme",
                "transport": "http",
                "url": "https://acme.internal/mcp",
                "auth_type": "bearer",
                "api_key_env": "ACME_MCP_TOKEN",
            }
        ],
        "bindings": {
            "default": False,
            "channels": ["slack:C0123"],
            "users": ["u_alice"],
        },
    }


def test_agent_file_parses_all_fields() -> None:
    af = agent_config.AgentFile.model_validate(_valid_doc())
    assert af.name == "support"
    assert af.version == 7
    assert af.tenant_id == "acme"
    assert af.team_id == "t1"
    assert af.allowed_tools == ["search_*", "acme__*"]
    assert af.plugins == ["acme"]
    assert af.features == {"code_execution": True}
    assert af.bindings.channels == ["slack:C0123"]
    assert af.bindings.users == ["u_alice"]
    # inline mcp_servers reuse the config McpServerSettings model
    assert len(af.mcp_servers) == 1
    assert af.mcp_servers[0].id == "acme"
    assert af.mcp_servers[0].api_key_env == "ACME_MCP_TOKEN"


def test_agent_file_defaults() -> None:
    af = agent_config.AgentFile.model_validate({"name": "bare", "version": 1})
    assert af.skills_dir is None
    assert af.allowed_skills == []
    assert af.plugins == []
    assert af.allowed_tools == []
    assert af.mcp_servers == []
    assert af.features == {}
    assert af.tenant_id == "default"
    assert af.team_id is None
    assert af.bindings.default is False
    assert af.bindings.channels == []
    assert af.bindings.users == []


@pytest.mark.parametrize("missing", ["name", "version"])
def test_agent_file_missing_required_rejected(missing: str) -> None:
    doc = _valid_doc()
    del doc[missing]
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_agent_file_unknown_field_rejected() -> None:
    doc = _valid_doc()
    doc["surprise"] = "nope"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


def test_load_agent_file_reads_yaml(tmp_path) -> None:
    agent_dir = tmp_path / "support"
    agent_dir.mkdir()
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    af = agent_config.load_agent_file(agent_dir)
    assert af.name == "support"
    assert af.version == 7


def test_load_agent_file_dir_name_mismatch_rejected(tmp_path) -> None:
    agent_dir = tmp_path / "helpdesk"
    agent_dir.mkdir()
    # in-file name is "support" but the directory is "helpdesk"
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    with pytest.raises(ValueError) as exc:
        agent_config.load_agent_file(agent_dir)
    assert "helpdesk" in str(exc.value)
    assert "support" in str(exc.value)


# ── scan + index (§2) ─────────────────────────────────────────────────────────


def _write_agent(root, name: str, **overrides) -> None:
    doc = {"name": name, "version": 1}
    doc.update(overrides)
    agent_dir = root / name
    agent_dir.mkdir(parents=True)
    (agent_dir / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_build_index_maps_names_channels_users_default(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "support",
        bindings={"channels": ["slack:C123"], "users": ["u_alice"]},
    )
    _write_agent(
        tmp_path,
        "sales",
        bindings={"default": True, "channels": ["telegram:-100"], "users": ["u_bob"]},
    )
    index = agent_config.build_index(tmp_path)

    assert index.get("support").name == "support"
    assert index.get("sales").name == "sales"
    assert index.get("ghost") is None

    assert index.agent_for_channel("slack", "C123") == "support"
    assert index.agent_for_channel("telegram", "-100") == "sales"
    assert index.agent_for_channel("slack", "nope") is None

    assert index.agent_for_user("u_alice") == "support"
    assert index.agent_for_user("u_bob") == "sales"
    assert index.agent_for_user("nobody") is None

    assert index.default_agent() == "sales"


def test_build_index_missing_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path / "does-not-exist")
    assert index.get("anything") is None
    assert index.default_agent() is None


def test_build_index_empty_dir_is_empty(tmp_path) -> None:
    index = agent_config.build_index(tmp_path)
    assert index.default_agent() is None
    assert index.agent_for_channel("slack", "C1") is None


def test_build_index_dir_name_mismatch_fails_fast(tmp_path) -> None:
    bad = tmp_path / "helpdesk"
    bad.mkdir()
    (bad / "agent.yaml").write_text(yaml.safe_dump(_valid_doc()), encoding="utf-8")
    with pytest.raises(ValueError):
        agent_config.build_index(tmp_path)


def test_scan_sets_current_index(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(tmp_path))
    _write_agent(tmp_path, "support", bindings={"default": True})
    agent_config.scan()
    assert agent_config.current().get("support").name == "support"
    assert agent_config.current().default_agent() == "support"


# ── conflict detection (§2.3) ─────────────────────────────────────────────────


def test_duplicate_channel_binding_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"channels": ["slack:C123"]})
    _write_agent(tmp_path, "sales", bindings={"channels": ["slack:C123"]})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "slack:C123" in msg
    assert "support" in msg and "sales" in msg


def test_duplicate_user_binding_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"users": ["u_alice"]})
    _write_agent(tmp_path, "sales", bindings={"users": ["u_alice"]})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    assert "u_alice" in str(exc.value)


def test_multiple_default_agents_fails_fast(tmp_path) -> None:
    _write_agent(tmp_path, "support", bindings={"default": True})
    _write_agent(tmp_path, "sales", bindings={"default": True})
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "support" in msg and "sales" in msg


# ── secret rejection (§2.5) ───────────────────────────────────────────────────


def test_inline_secret_in_mcp_rejected(tmp_path) -> None:
    # An mcp_servers entry that puts a live token where an env reference belongs.
    _write_agent(
        tmp_path,
        "support",
        mcp_servers=[{"id": "acme", "api_key_env": "sk-live-0123456789abcdefghijABCDEF"}],
    )
    with pytest.raises(ValueError) as exc:
        agent_config.build_index(tmp_path)
    msg = str(exc.value)
    assert "support" in msg
    assert "api_key_env" in msg


def test_env_reference_accepted(tmp_path) -> None:
    _write_agent(
        tmp_path,
        "support",
        mcp_servers=[{"id": "acme", "api_key_env": "ACME_MCP_TOKEN"}],
    )
    index = agent_config.build_index(tmp_path)  # no raise
    assert index.get("support").mcp_servers[0].api_key_env == "ACME_MCP_TOKEN"


def test_long_system_prompt_not_flagged_as_secret(tmp_path) -> None:
    # The secret scan targets MCP/connector defs, not free-text prompts.
    _write_agent(
        tmp_path,
        "support",
        system_prompt="You are a helpful assistant with supercalifragilisticexpialidocious skills.",
    )
    index = agent_config.build_index(tmp_path)  # no raise
    assert index.get("support") is not None


# ── single-file agent home (single-agent-config-file change) ──────────────────


def _write_home_agent(home, name: str, **overrides) -> None:
    """Write a home-root agent.yaml (no <name>/ subdir)."""
    doc = {"name": name, "version": 1}
    doc.update(overrides)
    (home / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")


def test_load_agent_home_file_skips_dir_name_check(tmp_path) -> None:
    # Home-root agent.yaml: `name` need not match any directory name.
    _write_home_agent(tmp_path, "whatever-name")
    agent = agent_config.load_agent_home_file(tmp_path / "agent.yaml")
    assert agent.name == "whatever-name"


def test_load_agent_home_file_still_rejects_inline_secret(tmp_path) -> None:
    _write_home_agent(
        tmp_path,
        "support",
        mcp_servers=[
            {
                "id": "acme",
                "transport": "http",
                "url": "https://acme.internal/mcp",
                "auth_type": "bearer",
                "api_key_env": "xoxb-1234567890-abcdefABCDEF",  # looks like a real secret
            }
        ],
    )
    with pytest.raises(ValueError):
        agent_config.load_agent_home_file(tmp_path / "agent.yaml")


def test_build_index_prefers_home_file_as_sole_default(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    # A multi-scan agents dir also exists; it must be ignored when home file is present.
    agents_dir = home / "config" / "agents"
    agents_dir.mkdir(parents=True)
    _write_agent(agents_dir, "other")
    # Home-root agent.yaml, bindings.default false -> still forced default.
    _write_home_agent(home, "deployed", bindings={"default": False, "channels": ["slack:C9"]})
    monkeypatch.setenv("FLEETENT_HOME", str(home))

    index = agent_config.build_index()

    assert set(index.agents) == {"deployed"}  # multi-scan ignored
    assert index.default == "deployed"  # forced default
    assert index.by_channel.get("slack:C9") == "deployed"
    assert index.get("other") is None


def test_build_index_falls_back_to_multiscan_without_home_file(tmp_path, monkeypatch) -> None:
    home = tmp_path / "home"
    home.mkdir()
    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    _write_agent(agents_dir, "a", bindings={"default": True})
    _write_agent(agents_dir, "b")
    monkeypatch.setenv("FLEETENT_HOME", str(home))  # no home-root agent.yaml
    monkeypatch.setenv("FLEETENT_AGENTS_DIR", str(agents_dir))  # explicit multi-scan dir

    index = agent_config.build_index()

    assert set(index.agents) == {"a", "b"}
    assert index.default == "a"  # multiscan: default decided by bindings.default


def test_repo_agent_yaml_example_loads_as_home_file() -> None:
    """The shipped single-agent root template parses with the home-file loader."""
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    example = repo / "config" / "agent.yaml.example"
    assert example.is_file(), "config/agent.yaml.example must exist (installer template)"
    agent = agent_config.load_agent_home_file(example)
    assert agent.name  # non-empty
    assert agent.version >= 1
