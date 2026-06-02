"""Unit tests for askit_runner (pure command mapping / whitelist / masking)."""

import pytest

from fleetent.platform.askit_console import askit_runner as r


def test_build_command_known():
    assert r.build_command("build", "build") == ["askit", "build"]
    assert r.build_command("override", "promote") == ["askit", "override", "promote"]


def test_build_command_with_params():
    argv = r.build_command("deploy", "deploy", {"target": "fleetent", "dry-run": True})
    assert "--target" in argv and "fleetent" in argv
    assert "--dry-run" in argv


def test_build_command_unknown_rejected():
    with pytest.raises(ValueError):
        r.build_command("build", "rm-rf")
    with pytest.raises(ValueError):
        r.build_command("bogus", "x")


def test_build_command_rejects_injection():
    with pytest.raises(ValueError):
        r.build_command("deploy", "deploy", {"target": "a; rm -rf /"})
    with pytest.raises(ValueError):
        r.build_command("deploy", "deploy", {"bad key": "v"})


def test_readonly_and_high_risk_flags():
    assert r.is_readonly("build", "check") is True
    assert r.is_readonly("deploy", "deploy") is False
    assert r.is_high_risk("deploy") is True
    assert r.is_high_risk("build") is False


def test_mask_output():
    masked = r.mask_output("ok\nGITHUB_TOKEN=ghp_secret\napi_key: abc123")
    assert "ghp_secret" not in masked
    assert "abc123" not in masked
    assert "ok" in masked


def test_run_uses_subprocess_seam(monkeypatch):
    monkeypatch.setattr(r, "run_subprocess", lambda argv: ("done TOKEN=xyz", "", 0))
    out = r.run("build", "build")
    assert out["exit_code"] == 0
    assert "xyz" not in out["stdout"]  # masked
    assert out["argv"] == ["askit", "build"]
    assert out["askit_version"] == r.ASKIT_VERSION


def test_serial_command_detection():
    assert r.is_serial("build", "build") is True
    assert r.is_serial("deploy", "deploy") is True
    assert r.is_serial("override", "promote") is True
    assert r.is_serial("build", "check") is False
    assert r.is_serial("override", "review") is False


def test_extract_pr_url():
    assert r.extract_pr_url("promoted\nPR: https://git.example.com/pr/7 done") == (
        "https://git.example.com/pr/7"
    )
    assert r.extract_pr_url("no link here") is None


def test_parse_cron_diff():
    diff = r.parse_cron_diff("+ added-task\n- missing-task\n~ changed-task\nuntouched")
    assert diff == {
        "added": ["added-task"],
        "missing": ["missing-task"],
        "changed": ["changed-task"],
    }


def test_parse_doctor_ryg():
    items = r.parse_doctor("GREEN: ok\nYELLOW: warn\nRED: fail\nplain line")
    assert items == [
        {"level": "green", "message": "ok"},
        {"level": "yellow", "message": "warn"},
        {"level": "red", "message": "fail"},
    ]
