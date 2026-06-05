"""Process-level deployment knobs resolve from the active agent (runtime-read-agent-config).

A standalone single-agent process reads session disk / disabled_skills / provider breaker
from the active agent; multi-agent / no-agent falls back to Settings defaults.
"""

from fleetent import agent_config
from fleetent.agent_config import AgentConfigIndex, AgentFile, default_models


def _publish_single(**fields) -> None:
    agent = AgentFile(name="a", version=1, models=default_models(), **fields)
    agent_config._index = AgentConfigIndex(
        agents={"a": agent}, by_channel={}, by_user={}, default="a"
    )


def test_session_config_from_active_agent() -> None:
    from fleetent.session import manager

    _publish_single(session_ttl_days=7, session_max_count=42)
    cfg = manager._default_config()
    assert cfg["max_count"] == 42
    assert cfg["ttl_seconds"] == 7 * 86400


def test_session_config_falls_back_without_agent() -> None:
    agent_config._index = AgentConfigIndex(agents={}, by_channel={}, by_user={}, default=None)
    from fleetent.session import manager

    cfg = manager._default_config()
    assert cfg["max_count"] == 10000  # Settings default


def test_disabled_skills_from_active_agent() -> None:
    from fleetent.skills import registry

    _publish_single(disabled_skills=["x", "y"])
    assert registry._resolve_disabled_skills(None) == {"x", "y"}


def test_provider_health_config_from_active_agent() -> None:
    import fleetent.model.provider_health as ph

    _publish_single(provider_failure_threshold=9, provider_cooldown_seconds=120)
    cfg = ph._default_config()
    assert cfg["failure_threshold"] == 9
    assert cfg["cooldown_seconds"] == 120
