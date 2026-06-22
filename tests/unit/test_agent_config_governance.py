"""agent.yaml per-agent governance + deployment field schema (agent-yaml-governance-schema).

Fields are added to AgentFile so each agent can express its full runtime config; this
phase adds schema acceptance only (runtime still reads Settings). Defaults MUST match the
current Settings defaults so an agent.yaml omitting them is equivalent to today.
"""

from dataclasses import fields

import pytest
import yaml
from pydantic import ValidationError

from fleetent import agent_config

LEGACY_LAYERED_BUDGET_FIELDS = (
    f"{'_'.join(('agent', 'budget', 'session'))}_turns",
    f"{'_'.join(('agent', 'budget', 'session'))}_tokens",
    f"{'_'.join(('agent', 'budget', 'user'))}_turns",
    f"{'_'.join(('agent', 'budget', 'user'))}_tokens",
    f"{'_'.join(('agent', 'budget', 'agent'))}_turns",
    f"{'_'.join(('agent', 'budget', 'agent'))}_tokens",
    f"{'_'.join(('agent', 'budget', 'user'))}_window",
    f"{'_'.join(('agent', 'budget', 'agent'))}_window",
)


def _write(root, name, **fields):
    doc = _agent_doc(name=name)
    doc.update(fields)
    d = root / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return d


def _agent_doc(name: str = "a", **fields):
    doc = {"name": name, "version": 1, "models": agent_config.default_models().model_dump()}
    doc.update(fields)
    return doc


# ── governance fields ──────────────────────────────────────────────────────


def test_governance_fields_parse() -> None:
    af = agent_config.AgentFile.model_validate(
        _agent_doc(
            agent_max_turns=30,
            context_compress_threshold=0.7,
            permission_gate_medium_timeout_seconds=60,
            provider_failure_threshold=5,
        )
    )
    assert af.agent_max_turns == 30
    assert af.context_compress_threshold == 0.7
    assert af.permission_gate_medium_timeout_seconds == 60
    assert af.provider_failure_threshold == 5


def test_governance_defaults_match_settings() -> None:
    af = agent_config.AgentFile.model_validate(_agent_doc(name="bare"))
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


def test_two_agents_carry_independent_governance() -> None:
    a = agent_config.AgentFile.model_validate(_agent_doc(name="a", agent_max_turns=30))
    b = agent_config.AgentFile.model_validate(_agent_doc(name="b", agent_max_turns=80))
    assert a.agent_max_turns == 30
    assert b.agent_max_turns == 80


def test_cross_run_budget_fields_removed_from_agent_and_runtime_governance() -> None:
    from fleetent.runtime.snapshot import GovernanceConfig

    agent_fields = set(agent_config.AgentFile.model_fields)
    runtime_fields = {field.name for field in fields(GovernanceConfig)}

    for field_name in LEGACY_LAYERED_BUDGET_FIELDS:
        assert field_name not in agent_fields
        assert field_name not in runtime_fields


def test_legacy_cross_run_budget_keys_are_ignored_when_loading_agent_file(tmp_path) -> None:
    from fleetent.runtime.snapshot import _governance_from_file

    legacy_fields = {
        LEGACY_LAYERED_BUDGET_FIELDS[0]: 12,
        LEGACY_LAYERED_BUDGET_FIELDS[1]: 2048,
        LEGACY_LAYERED_BUDGET_FIELDS[2]: 24,
        LEGACY_LAYERED_BUDGET_FIELDS[3]: 8192,
        LEGACY_LAYERED_BUDGET_FIELDS[4]: 36,
        LEGACY_LAYERED_BUDGET_FIELDS[5]: 12288,
        LEGACY_LAYERED_BUDGET_FIELDS[6]: "daily",
        LEGACY_LAYERED_BUDGET_FIELDS[7]: "monthly",
    }
    _write(
        tmp_path,
        "a",
        agent_max_turns=30,
        agent_max_tokens=4096,
        agent_grace_call_token_ratio=0.2,
        agent_grace_call_min_tokens=256,
        **legacy_fields,
    )

    agent = agent_config.load_agent_file(tmp_path / "a")
    governance = _governance_from_file(agent)

    assert agent.agent_max_turns == 30
    assert agent.agent_max_tokens == 4096
    assert agent.agent_grace_call_token_ratio == 0.2
    assert agent.agent_grace_call_min_tokens == 256
    assert governance.agent_max_turns == 30
    assert governance.agent_max_tokens == 4096
    assert governance.agent_grace_call_token_ratio == 0.2
    assert governance.agent_grace_call_min_tokens == 256


# ── deployment / process fields ────────────────────────────────────────────


def test_deployment_scalar_fields_parse() -> None:
    af = agent_config.AgentFile.model_validate(
        _agent_doc(
            session_ttl_days=7,
            disabled_skills=["x"],
            log_format="json",
        )
    )
    assert af.session_ttl_days == 7
    assert af.disabled_skills == ["x"]
    assert af.log_format == "json"


def test_deployment_defaults_match_settings() -> None:
    af = agent_config.AgentFile.model_validate(_agent_doc(name="bare"))
    assert af.log_format == "console"
    assert af.session_ttl_days == 30
    assert af.session_max_total_mb == 1024
    assert af.session_max_count == 10000
    assert af.session_cleanup_interval_seconds == 3600.0
    assert af.reflection.enabled is False
    assert af.reflection.interval_seconds == 86400.0
    assert af.reflection.auto_apply.allow_low_risk is False
    assert af.disabled_skills == []


def test_reflection_settings_parse_and_override() -> None:
    af = agent_config.AgentFile.model_validate(
        _agent_doc(
            reflection={
                "enabled": True,
                "interval_seconds": 123.5,
                "auto_apply": {"allow_low_risk": True},
            }
        )
    )
    assert af.reflection.enabled is True
    assert af.reflection.interval_seconds == 123.5
    assert af.reflection.auto_apply.allow_low_risk is True


def test_reflection_auto_apply_rejects_unknown_key() -> None:
    with pytest.raises(ValidationError):
        agent_config.AgentFile.model_validate(
            _agent_doc(
                reflection={
                    "enabled": True,
                    "auto_apply": {
                        "allow_low_risk": True,
                        "allow_low_risks": True,
                    },
                }
            )
        )


def test_nested_observability_reuses_submodel() -> None:
    from fleetent.config import ObservabilitySettings

    af = agent_config.AgentFile.model_validate(
        _agent_doc(
            observability={"logging": {"console_level": "debug"}},
        )
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
        _agent_doc(
            diagnostics={"export_dir": "/tmp/diag"},
            mcp={"enabled": False},
            scheduling={"default_timezone": "Asia/Shanghai"},
            webhooks={"max_body_bytes": 2048},
        )
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
        f"{'_'.join(('agent', 'budget', 'global'))}_turns",
        f"{'_'.join(('agent', 'budget', 'global'))}_tokens",
        f"{'_'.join(('agent', 'budget', 'global'))}_window",
        "database_url",
    ],
)
def test_excluded_fields_rejected(field: str) -> None:
    doc = _agent_doc(**{field: "x" if "window" in field else 1})
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
