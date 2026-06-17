"""Code-execution enablement decision (per-agent-sandbox-enablement).

Mode collapses to {OFF, ON}: ON means the backend is available (runtime sandbox
capability), OFF means it is not. There is no global tri-state read from platform.yaml
anymore — per-agent `features.code_execution` is the sole policy input, gated by the
runtime capability. `get_effective_mode` derives ON/OFF purely from the backend probe.
"""

from __future__ import annotations

import pytest

import fleetent.integrations.sandbox.enablement as se
from fleetent.integrations.sandbox.enablement import Mode, is_code_execution_enabled


def test_mode_members_are_off_on_only():
    assert Mode.OFF == "off"
    assert Mode.ON == "on"
    assert not hasattr(Mode, "SELECTIVE")
    assert not hasattr(Mode, "ALL")


@pytest.mark.parametrize("code_execution", [None, True, False])
def test_off_always_disabled(code_execution):
    assert is_code_execution_enabled(Mode.OFF, code_execution) is False


def test_on_enabled_unless_explicit_false():
    # Preserves the old `all` semantics: unset/true on, explicit false off.
    assert is_code_execution_enabled(Mode.ON, None) is True
    assert is_code_execution_enabled(Mode.ON, True) is True
    assert is_code_execution_enabled(Mode.ON, False) is False


class _Backend:
    def __init__(self, available: bool) -> None:
        self._available = available

    async def available(self) -> bool:
        return self._available


async def test_get_effective_mode_on_when_backend_available(monkeypatch):
    monkeypatch.setattr(se, "_effective_mode_cache", None)
    assert await se.get_effective_mode(_Backend(True)) is Mode.ON


async def test_get_effective_mode_off_when_backend_unavailable(monkeypatch):
    monkeypatch.setattr(se, "_effective_mode_cache", None)
    assert await se.get_effective_mode(_Backend(False)) is Mode.OFF


async def test_get_effective_mode_caches_probe(monkeypatch):
    monkeypatch.setattr(se, "_effective_mode_cache", None)
    calls = {"n": 0}

    class _Counting:
        async def available(self) -> bool:
            calls["n"] += 1
            return True

    b = _Counting()
    first = await se.get_effective_mode(b)
    second = await se.get_effective_mode(b)
    assert first is Mode.ON and second is Mode.ON
    assert calls["n"] == 1  # probed once, then cached


def test_no_platform_yaml_mode_loader():
    # The tri-state mode loader + its platform.yaml read are removed.
    assert not hasattr(se, "load_sandbox_mode")
    assert not hasattr(se, "SETTINGS_PATH")
