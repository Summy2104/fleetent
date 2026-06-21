"""CLI one-shot: /user command interception before the agent loop.

Pure entrypoint dispatch with run() and config scan mocked (no LLM, no DB).
"""

from __future__ import annotations

from fleetent import __main__ as mainmod
from fleetent import agent_config
from fleetent.runtime import user_instructions as ui


class _Idx:
    def default_agent(self) -> str:
        return "default"


def _stub_config(monkeypatch) -> None:
    monkeypatch.setattr(agent_config, "scan", lambda *a, **k: None)
    monkeypatch.setattr(agent_config, "current", lambda: _Idx())


def test_cli_user_command_intercepted(monkeypatch, capsys) -> None:
    _stub_config(monkeypatch)
    ran: list[str] = []
    monkeypatch.setattr(mainmod, "run", lambda s: ran.append(s) or "RAN")

    mainmod.main(["/user", "用中文回答"])

    out = capsys.readouterr().out
    assert "已追加" in out
    assert ran == []  # the agent loop never ran
    assert "用中文回答" in ui.load("default")


def test_cli_normal_prompt_runs(monkeypatch, capsys) -> None:
    _stub_config(monkeypatch)
    ran: list[str] = []
    monkeypatch.setattr(mainmod, "run", lambda s: ran.append(s) or "REPLY")

    mainmod.main(["你好"])

    assert ran == ["你好"]
    assert "REPLY" in capsys.readouterr().out
