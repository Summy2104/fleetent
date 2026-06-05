"""Loop governance resolution reads the per-run GovernanceConfig (runtime-read-agent-config).

Precedence: explicit call param > governance (agent config) > Settings/default fallback.
When governance is None the helpers fall back to the historical Settings defaults so the
behaviour is unchanged.
"""

from fleetent.runtime import loop
from fleetent.runtime.snapshot import GovernanceConfig


def test_budget_config_uses_governance() -> None:
    gov = GovernanceConfig(agent_max_turns=30, agent_max_tokens=999)
    cfg = loop._resolve_budget_config(None, None, gov)
    assert cfg.max_turns == 30
    assert cfg.max_tokens == 999


def test_budget_config_call_param_overrides_governance() -> None:
    gov = GovernanceConfig(agent_max_turns=30, agent_max_tokens=999)
    cfg = loop._resolve_budget_config(5, 7, gov)
    assert cfg.max_turns == 5
    assert cfg.max_tokens == 7


def test_guardrail_threshold_uses_governance() -> None:
    assert (
        loop._resolve_guardrail_threshold(None, GovernanceConfig(guardrail_repeat_threshold=9)) == 9
    )


def test_parallel_max_uses_governance() -> None:
    assert loop._resolve_parallel_max(GovernanceConfig(agent_tool_parallel_max=2)) == 2


def test_default_tool_timeout_uses_governance() -> None:
    assert (
        loop._resolve_default_tool_timeout(GovernanceConfig(tool_default_timeout_seconds=15.0))
        == 15.0
    )


def test_loop_config_uses_governance() -> None:
    gov = GovernanceConfig(agent_loop_repeat_threshold=4, loop_detect_ignore_arg_keys=("k",))
    threshold, ignore = loop._resolve_loop_config(None, None, gov)
    assert threshold == 4
    assert ignore == ["k"]


def test_none_governance_falls_back_to_settings_default() -> None:
    # No governance: helpers fall back to the historical Settings defaults.
    assert loop._resolve_default_tool_timeout(None) == 30.0
    assert loop._resolve_parallel_max(None) == 8
    assert loop._resolve_guardrail_threshold(None, None) == 3
