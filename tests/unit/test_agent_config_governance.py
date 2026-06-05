"""agent.yaml per-agent governance + deployment field schema (agent-yaml-governance-schema).

Fields are added to AgentFile so each agent can express its full runtime config; this
phase adds schema acceptance only (runtime still reads Settings). Defaults MUST match the
current Settings defaults so an agent.yaml omitting them is equivalent to today.
"""

import pytest
import yaml
from pydantic import ValidationError

from fleetent import agent_config


def _write(root, name, **fields):
    doc = {"name": name, "version": 1}
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return d


# ── governance fields ──────────────────────────────────────────────────────


def test_governance_fields_parse() -> None:
    af = agent_config.AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "agent_max_turns": 30,
            "context_compress_threshold": 0.7,
            "agent_budget_user_tokens": 5000,
            "permission_gate_medium_timeout_seconds": 60,
            "provider_failure_threshold": 5,
        }
    )
    assert af.agent_max_turns == 30
    assert af.context_compress_threshold == 0.7
    assert af.agent_budget_user_tokens == 5000
    assert af.permission_gate_medium_timeout_seconds == 60
    assert af.provider_failure_threshold == 5


def test_governance_defaults_match_settings() -> None:
    af = agent_config.AgentFile.model_validate({"name": "bare", "version": 1})
    # Defaults must equal current Settings defaults (config.py).
    assert af.agent_max_turns == 50
    assert af.agent_max_consecutive_failures == 3
    assert af.tool_default_timeout_seconds == 30.0
    assert af.sub_agent_timeout_seconds == 300
    assert af.context_max_tokens == 200_000
    assert af.context_compress_threshold == 0.8
    assert af.context_keep_recent == 10
    assert af.agent_max_tokens == -1
    assert af.agent_loop_repeat_threshold == 3
    assert af.guardrail_repeat_threshold == 3
    assert af.agent_tool_parallel_max == 8
    assert af.loop_detect_ignore_arg_keys == []
    assert af.permission_gate_medium_timeout_seconds == 300
    assert af.permission_gate_high_timeout_seconds == 3600
    assert af.provider_failure_threshold == 3
    assert af.provider_cooldown_seconds == 60
    # layered budget (session/user/agent dims only)
    assert af.agent_budget_session_turns == -1
    assert af.agent_budget_user_window == "weekly"
    assert af.agent_budget_agent_window == "weekly"


def test_two_agents_carry_independent_governance() -> None:
    a = agent_config.AgentFile.model_validate({"name": "a", "version": 1, "agent_max_turns": 30})
    b = agent_config.AgentFile.model_validate({"name": "b", "version": 1, "agent_max_turns": 80})
    assert a.agent_max_turns == 30
    assert b.agent_max_turns == 80


# ── deployment / process fields ────────────────────────────────────────────


def test_deployment_scalar_fields_parse() -> None:
    af = agent_config.AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "microsandbox_url": "http://sandbox:7777",
            "session_ttl_days": 7,
            "image_gen_url": "http://img:8000",
            "vision_model": "qwen-vl",
            "disabled_skills": ["x"],
            "log_format": "json",
        }
    )
    assert af.microsandbox_url == "http://sandbox:7777"
    assert af.session_ttl_days == 7
    assert af.image_gen_url == "http://img:8000"
    assert af.vision_model == "qwen-vl"
    assert af.disabled_skills == ["x"]
    assert af.log_format == "json"


def test_deployment_defaults_match_settings() -> None:
    af = agent_config.AgentFile.model_validate({"name": "bare", "version": 1})
    assert af.microsandbox_url == "http://host.docker.internal:7777"
    assert af.log_format == "console"
    assert af.session_ttl_days == 30
    assert af.session_max_total_mb == 1024
    assert af.session_max_count == 10000
    assert af.session_cleanup_interval_seconds == 3600.0
    assert af.image_gen_url == ""
    assert af.image_gen_model == "default"
    assert af.vision_url == ""
    assert af.vision_model == "default"
    assert af.disabled_skills == []


def test_nested_observability_reuses_submodel() -> None:
    from fleetent.config import ObservabilitySettings

    af = agent_config.AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "observability": {"logging": {"console_level": "debug"}},
        }
    )
    assert isinstance(af.observability, ObservabilitySettings)
    assert af.observability.logging.console_level == "debug"


def test_nested_blocks_reuse_submodels() -> None:
    from fleetent.config import (
        DiagnosticsSettings,
        McpSettings,
        SchedulingSettings,
        WebhooksSettings,
    )

    af = agent_config.AgentFile.model_validate(
        {
            "name": "a",
            "version": 1,
            "diagnostics": {"export_dir": "/tmp/diag"},
            "mcp": {"enabled": False},
            "scheduling": {"default_timezone": "Asia/Shanghai"},
            "webhooks": {"max_body_bytes": 2048},
        }
    )
    assert isinstance(af.diagnostics, DiagnosticsSettings)
    assert isinstance(af.mcp, McpSettings)
    assert isinstance(af.scheduling, SchedulingSettings)
    assert isinstance(af.webhooks, WebhooksSettings)
    assert af.diagnostics.export_dir == "/tmp/diag"
    assert af.mcp.enabled is False
    assert af.scheduling.default_timezone == "Asia/Shanghai"
    assert af.webhooks.max_body_bytes == 2048


# ── excluded: global budget + database_url ─────────────────────────────────


@pytest.mark.parametrize(
    "field",
    [
        "agent_budget_global_turns",
        "agent_budget_global_tokens",
        "agent_budget_global_window",
        "database_url",
    ],
)
def test_excluded_fields_rejected(field: str) -> None:
    doc = {"name": "a", "version": 1, field: "x" if "window" in field else 1}
    if field == "database_url":
        doc[field] = "sqlite:///x.db"
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(doc)


# ── inline-secret rejection covers new fields ──────────────────────────────


def test_inline_secret_in_governance_payload_rejected(tmp_path) -> None:
    # A secret-bearing *_env-style position carrying an inline secret must be rejected.
    _write(
        tmp_path,
        "a",
        embedding={"backend": "openai", "api_key_env": "sk-livesecret0123456789abcdefghij"},
    )
    with pytest.raises(ValueError, match="inline secret"):
        agent_config.load_agent_file(tmp_path / "a")
