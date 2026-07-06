"""Unit tests for workflow definition directory resolution and file loading.

Pure filesystem read + YAML parse (no DB/LLM). Uses tmp_path + env monkeypatch
per the path-precedence testing convention.
"""

import pytest

from fleetent.workflow.errors import WorkflowDefinitionError, WorkflowNotFoundError


def _write(dir_, name, body):
    dir_.mkdir(parents=True, exist_ok=True)
    (dir_ / f"{name}.yaml").write_text(body)


_DEMO = """
name: demo
description: demo flow
steps:
  - id: hello
    type: notify
    text: "hi"
"""


def test_env_override_dir(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    wf_dir = tmp_path / "wf"
    _write(wf_dir, "demo", _DEMO)
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    wf = loader.load_definition("demo")
    assert wf.name == "demo"


def test_default_dir_under_home(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    monkeypatch.delenv("FLEETENT_WORKFLOWS_DIR", raising=False)
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path))
    _write(tmp_path / "workflows", "demo", _DEMO)
    wf = loader.load_definition("demo")
    assert wf.name == "demo"


def test_not_found_lists_available(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    wf_dir = tmp_path / "wf"
    _write(wf_dir, "demo", _DEMO)
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    with pytest.raises(WorkflowNotFoundError, match="demo"):
        loader.load_definition("ghost")


def test_missing_dir_is_empty_not_error(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(tmp_path / "nope"))
    assert loader.list_definitions() == []


def test_list_reports_invalid_without_crashing(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    wf_dir = tmp_path / "wf"
    _write(wf_dir, "good", _DEMO)
    _write(wf_dir, "bad", "name: bad\nsteps: []\n")  # empty steps → invalid
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    listed = {d["name"]: d for d in loader.list_definitions()}
    assert listed["good"]["valid"] is True
    assert listed["bad"]["valid"] is False
    assert listed["bad"]["error"]


def test_load_invalid_raises_definition_error(tmp_path, monkeypatch):
    from fleetent.workflow import loader

    wf_dir = tmp_path / "wf"
    _write(wf_dir, "bad", "name: bad\nsteps: []\n")
    monkeypatch.setenv("FLEETENT_WORKFLOWS_DIR", str(wf_dir))
    with pytest.raises(WorkflowDefinitionError):
        loader.load_definition("bad")
