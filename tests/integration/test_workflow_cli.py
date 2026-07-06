"""Integration: `fleetent workflow list|run` CLI."""

import pytest


def _write(dir_, name, body):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{name}.yaml").write_text(body)


_AGENT_WF = """
name: demo
description: demo
steps:
  - id: a
    type: agent
    prompt: "hello"
"""


def test_list_reports_invalid_without_crash(tmp_path, monkeypatch, capsys):
    from fleetent.workflow import cli

    wf_dir = tmp_path / "wf"
    _write(wf_dir, "good", _AGENT_WF)
    _write(wf_dir, "bad", "name: bad\nsteps: []\n")
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    cli.main(["list"])
    out = capsys.readouterr().out
    assert "good: ok" in out
    assert "bad: INVALID" in out


def test_run_drives_to_terminal_and_prints_steps(tmp_path, monkeypatch, capsys):
    from fleetent.runtime import loop as agent_loop
    from fleetent.workflow import cli

    async def fake_run(messages, **kw):
        return "done"

    monkeypatch.setattr(agent_loop, "run", fake_run)
    wf_dir = tmp_path / "wf"
    _write(wf_dir, "demo", _AGENT_WF)
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path / "home"))

    cli.main(["run", "demo", "--home", str(tmp_path / "agenthome")])
    out = capsys.readouterr().out
    assert "[succeeded]" in out
    assert "a [succeeded]" in out
