"""Unit: materialize._apply_overrides logs (not silently drops) an invalid override.

Guards AAA-8267: a single bad field in config_overrides (e.g. a dangling model route) makes
the merged AgentFile fail validation; _apply_overrides falls back to base to keep
deploy/preview alive, but MUST surface an ERROR so the (possibly unrelated) bindings it
drops — like im.slack credentials — are diagnosable rather than silently gone.
"""

from __future__ import annotations

from fleetent.agent_config import AgentFile, default_models
from fleetent.platform.agent_lifecycle import materialize


class _RecordingLogger:
    def __init__(self) -> None:
        self.errors: list[tuple[str, dict]] = []

    def error(self, event: str, **kwargs: object) -> None:
        self.errors.append((event, kwargs))


def test_invalid_override_returns_base_and_logs_error(monkeypatch):
    base = AgentFile(name="bi-intern", version=1, models=default_models())
    # Dangling model route: 'vision' references a target not present in targets → validation fails.
    bad_override = {
        "models": {"targets": [], "routes": {"vision": [{"target": "vision-model"}]}}
    }

    fake = _RecordingLogger()
    monkeypatch.setattr(materialize, "_logger", fake)

    result = materialize._apply_overrides(base, bad_override)

    # Fallback to base preserved (deploy/preview never breaks).
    assert result is base
    # But the drop is now observable (not silent).
    assert fake.errors, "expected an ERROR log on invalid override, got none"
    event, kwargs = fake.errors[0]
    assert event == "agent_override_validation_failed"
    assert kwargs.get("agent") == "bi-intern"
