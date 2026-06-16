"""Integration: 封闭即免审批 cash-in driven by an agent.yaml config value.

The cash-in adds config + docs only — the disposition itself is the既有
`resolve_action_mode` fed by the runtime's `runtime_sandbox_capable`. This test
loads `action_gate_medium_mode: sandbox` from a real agent.yaml and proves the
end-to-end disposition: contained → SANDBOX (no approval); effective_mode OFF
(no docker) → fail-closed APPROVAL. No resolver/registry constant is touched.
"""

from __future__ import annotations

import yaml

from fleetent import agent_config
from fleetent.governance.action_gate import ActionMode, resolve_action_mode
from fleetent.integrations.sandbox import Mode
from fleetent.runtime.loop import runtime_sandbox_capable


def _write_agent(agents_dir, medium_mode):
    doc = {
        "name": "ops",
        "version": 1,
        "models": agent_config.default_models().model_dump(),
        "action_gate_medium_mode": medium_mode,
        "action_gate_high_mode": "approval",
    }
    d = agents_dir / "ops"
    d.mkdir(parents=True, exist_ok=True)
    (d / "agent.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return agent_config.load_agent_file(d)


def _gate(af, *, mode):
    return resolve_action_mode(
        "medium",
        medium_mode=af.action_gate_medium_mode,
        high_mode=af.action_gate_high_mode,
        sandbox_capable=runtime_sandbox_capable("run_code", mode, workspace_mount=True),
        force_ask=False,
    )


def test_config_sandbox_contained_runs_without_approval(tmp_path) -> None:
    af = _write_agent(tmp_path / "agents", "sandbox")
    assert af.action_gate_medium_mode == "sandbox"
    assert _gate(af, mode=Mode.ON) is ActionMode.SANDBOX


def test_config_sandbox_uncontained_fails_closed_to_approval(tmp_path) -> None:
    af = _write_agent(tmp_path / "agents", "sandbox")
    assert _gate(af, mode=Mode.OFF) is ActionMode.APPROVAL


def test_high_stays_approval_when_medium_relaxed(tmp_path) -> None:
    af = _write_agent(tmp_path / "agents", "sandbox")
    high = resolve_action_mode(
        "high",
        medium_mode=af.action_gate_medium_mode,
        high_mode=af.action_gate_high_mode,
        sandbox_capable=runtime_sandbox_capable("run_code", Mode.ON, workspace_mount=True),
        force_ask=False,
    )
    assert high is ActionMode.APPROVAL


def test_code_default_medium_mode_remains_approval() -> None:
    # The cash-in does NOT flip the code default —免审批 is an explicit deploy choice.
    af = agent_config.AgentFile(name="x", version=1, models=agent_config.default_models())
    assert af.action_gate_medium_mode == "approval"
