"""Tests for agent_apply_api + askit_console_api. Covers scenarios 58-73."""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.agent_management_console.agent_admin_store as agent_state
import fleetent.platform.askit_console.agent_apply_api as apply_api
import fleetent.platform.askit_console.askit_console_api as console
import fleetent.platform.askit_console.askit_runner as runner
import fleetent.user_store as user_store


def apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", "migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture
def client(tmp_path, monkeypatch):
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    for mod in (user_store, audit):
        monkeypatch.setattr(mod, "DB_PATH", db_path)
    user_store._init_db()
    audit._init_db()
    # askit subprocess: succeed by default
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: ("ok", "", 0))
    app = FastAPI()
    app.include_router(apply_api.router)
    app.include_router(console.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str, confirm: bool = False) -> dict:
    h = {"Authorization": f"Session {token}"}
    if confirm:
        h["X-Confirm"] = "true"
    return h


# --- agent apply / adopt (场景 68-73) ----------------------------------------


def test_apply_creates_managed(client, monkeypatch):  # 场景 68
    created = {}
    monkeypatch.setattr(apply_api, "get_agent_def", lambda name: None)
    monkeypatch.setattr(apply_api, "create_agent_def", lambda n, sp, at: created.update(n=n) or 7)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents/apply",
        headers=_hdr(token),
        json={"name": "ops", "system_prompt": "p", "allowed_tools": ["read_*"]},
    )
    assert r.json()["action"] == "created"
    assert r.json()["provenance"] == "managed"
    assert agent_state.get_state("ops")["provenance"] == "managed"


def test_apply_requires_admin(client, monkeypatch):
    monkeypatch.setattr(apply_api, "get_agent_def", lambda name: None)
    monkeypatch.setattr(apply_api, "create_agent_def", lambda n, sp, at: 1)
    token, _ = _session_for("viewer")
    r = client.post(
        "/admin/agents/apply", headers=_hdr(token), json={"name": "ops", "system_prompt": "p"}
    )
    assert r.status_code == 403


def test_apply_idempotent_and_bindings_untouched(client, monkeypatch):  # 场景 69
    updates = []
    monkeypatch.setattr(
        apply_api,
        "get_agent_def",
        lambda name: {"id": 5, "system_prompt": "old", "allowed_tools": []},
    )
    monkeypatch.setattr(apply_api, "update_agent_def", lambda n, sp, at: updates.append((n, sp)))
    # no create_agent_def call expected; no binding seam touched (none exists)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents/apply",
        headers=_hdr(token),
        json={"name": "ops", "system_prompt": "new", "allowed_tools": []},
    )
    assert r.json()["agent_id"] == 5  # same id, no rebuild
    assert updates == [("ops", "new")]


def test_apply_adopts_adhoc_keeping_id(client, monkeypatch):  # 场景 72 (adopt)
    agent_state.set_provenance("ops", "adhoc")  # pre-existing adhoc
    monkeypatch.setattr(
        apply_api,
        "get_agent_def",
        lambda name: {"id": 9, "system_prompt": "p", "allowed_tools": []},
    )
    monkeypatch.setattr(apply_api, "update_agent_def", lambda n, sp, at: None)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents/apply", headers=_hdr(token), json={"name": "ops", "system_prompt": "p"}
    )
    assert r.json()["action"] == "adopted"
    assert r.json()["agent_id"] == 9  # same agent_id, flipped to managed
    assert agent_state.get_state("ops")["provenance"] == "managed"


def test_apply_batch(client, monkeypatch):
    monkeypatch.setattr(apply_api, "get_agent_def", lambda name: None)
    monkeypatch.setattr(apply_api, "create_agent_def", lambda n, sp, at: 1)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/agents/apply:batch",
        headers=_hdr(token),
        json={"agents": [{"name": "a", "system_prompt": "p"}, {"name": "b", "system_prompt": "p"}]},
    )
    assert len(r.json()["applied"]) == 2


# --- console: series + run (场景 58/59) --------------------------------------


def test_series_grouped(client):  # 场景 58
    token, _ = _session_for("viewer")
    r = client.get("/admin/askit/series", headers=_hdr(token))
    series = {g["series"] for g in r.json()}
    assert {
        "authoring",
        "build",
        "deploy",
        "override",
        "cron",
        "env",
        "migrations",
        "deps",
    } == series


def test_run_build_records_logs(client, monkeypatch):  # 场景 59
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: ("building...\ndone", "", 0))
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "build", "command": "build", "workspace": "dev"},
    )
    assert r.json()["status"] == "succeeded"
    tid = r.json()["task_id"]
    detail = client.get(f"/admin/askit/tasks/{tid}", headers=_hdr(token))
    lines = [log["line"] for log in detail.json()["logs"]]
    assert "building..." in lines


# --- check gate (场景 60) + dry-run (场景 61/65) -----------------------------


def test_deploy_blocked_when_check_not_green(client, monkeypatch):  # 场景 60
    monkeypatch.setattr(console, "last_check_ok", lambda ws: False)
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),
        json={"series": "deploy", "command": "deploy", "workspace": "prod"},
    )
    assert r.status_code == 409


def test_deploy_requires_confirm(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run", headers=_hdr(token), json={"series": "deploy", "command": "deploy"}
    )
    assert r.status_code == 428


def test_migration_defaults_dry_run(client, monkeypatch):  # 场景 65
    seen = {}
    monkeypatch.setattr(
        runner, "run_subprocess", lambda argv: seen.update(argv=argv) or ("ok", "", 0)
    )
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),  # no confirm
        json={"series": "migrations", "command": "migrate-env"},
    )
    assert r.json()["dry_run"] is True
    assert "--dry-run" in seen["argv"]


# --- readonly vs write role (场景 66) ----------------------------------------


def test_viewer_can_run_readonly_not_write(client):  # 场景 66
    token, _ = _session_for("viewer")
    ok = client.post(
        "/admin/askit/run", headers=_hdr(token), json={"series": "build", "command": "check"}
    )
    assert ok.status_code == 200  # check is read-only
    denied = client.post(
        "/admin/askit/run", headers=_hdr(token), json={"series": "build", "command": "build"}
    )
    assert denied.status_code == 403


def test_unknown_command_422(client):
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run", headers=_hdr(token), json={"series": "build", "command": "nope"}
    )
    assert r.status_code == 422


def test_run_failure_records_exit_code(client, monkeypatch):
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: ("", "boom", 2))
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run", headers=_hdr(token), json={"series": "build", "command": "check"}
    )
    assert r.json()["status"] == "failed"
    assert r.json()["exit_code"] == 2


# --- workspace serial lock (场景 67) + streamed logs (场景 63) ----------------


def test_serial_write_command_uses_workspace_lock(client, monkeypatch):
    import contextlib

    import fleetent.platform.askit_console.askit_task_store as store

    seen: list[str] = []
    real = store.workspace_lock

    @contextlib.asynccontextmanager
    async def spy(workspace):
        seen.append(workspace or "_default")
        async with real(workspace):
            yield

    monkeypatch.setattr(store, "workspace_lock", spy)
    token, _ = _session_for("admin")
    client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "build", "command": "build", "workspace": "dev"},
    )
    assert "dev" in seen


def test_readonly_command_skips_workspace_lock(client, monkeypatch):
    import contextlib

    import fleetent.platform.askit_console.askit_task_store as store

    seen: list[str] = []
    real = store.workspace_lock

    @contextlib.asynccontextmanager
    async def spy(workspace):
        seen.append(workspace or "_default")
        async with real(workspace):
            yield

    monkeypatch.setattr(store, "workspace_lock", spy)
    token, _ = _session_for("viewer")
    client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "build", "command": "check", "workspace": "dev"},
    )
    assert seen == []


def test_task_log_stream_replays_logs_and_exit(client, monkeypatch):  # 场景 63
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: ("line-a\nline-b", "err-c", 0))
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "build", "command": "build", "workspace": "dev"},
    )
    tid = r.json()["task_id"]
    stream = client.get(f"/admin/askit/tasks/{tid}/stream", headers=_hdr(token))
    assert stream.status_code == 200
    body = stream.text
    assert "line-a" in body
    assert "line-b" in body
    assert "err-c" in body
    assert '"exit_code": 0' in body


def test_confirmed_migration_runs_without_dry_run_and_audits(client, monkeypatch):  # 场景 65
    seen: dict = {}
    monkeypatch.setattr(
        runner, "run_subprocess", lambda argv: seen.update(argv=argv) or ("ok", "", 0)
    )
    token, uid = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),  # explicit confirm cancels the default dry-run
        json={"series": "migrations", "command": "migrate-env"},
    )
    assert r.json()["dry_run"] is False
    assert "--dry-run" not in seen["argv"]
    tid = r.json()["task_id"]
    entries = audit.search_audit(action="askit.migrations.migrate-env")
    assert any(e["target_id"] == tid and e["detail"]["dry_run"] is False for e in entries)


# --- high-risk 2FA (任务 7.5/7.6, 场景 80-82) --------------------------------


def test_high_risk_deploy_requires_2fa_when_enabled(client):
    token, uid = _session_for("admin")
    auth.enable_2fa(uid)  # actor now has a second factor configured
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),  # confirmed but no X-2FA-Code
        json={"series": "deploy", "command": "deploy", "workspace": "prod"},
    )
    assert r.status_code == 403


def test_high_risk_deploy_passes_with_valid_2fa(client):
    token, uid = _session_for("admin")
    secret = auth.enable_2fa(uid)
    headers = _hdr(token, confirm=True)
    headers["X-2FA-Code"] = auth.totp(secret)
    r = client.post(
        "/admin/askit/run",
        headers=headers,
        json={"series": "deploy", "command": "deploy", "workspace": "prod"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "succeeded"


def test_promote_requires_2fa_when_enabled(client):
    token, uid = _session_for("admin")
    auth.enable_2fa(uid)
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),
        json={"series": "override", "command": "promote", "workspace": "dev"},
    )
    assert r.status_code == 403


def test_high_risk_without_2fa_configured_not_blocked(client):
    token, _ = _session_for("admin")  # no 2FA enabled for this actor
    headers = _hdr(token, confirm=True)
    headers["X-2FA-Code"] = ""  # nothing to verify against
    r = client.post(
        "/admin/askit/run",
        headers=headers,
        json={"series": "deploy", "command": "deploy", "workspace": "prod"},
    )
    assert r.status_code == 200


# --- cron diff + second confirmation (任务 9.3/9.4, 场景 51-54) ---------------


def test_cron_install_requires_confirm(client):
    token, _ = _session_for("admin")
    denied = client.post(
        "/admin/askit/run",
        headers=_hdr(token),  # no confirm
        json={"series": "cron", "command": "install", "workspace": "dev"},
    )
    assert denied.status_code == 428
    ok = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),
        json={"series": "cron", "command": "install", "workspace": "dev"},
    )
    assert ok.status_code == 200


def test_cron_diff_highlights_added_missing_changed(client, monkeypatch):
    out = "+ nightly-build\n- stale-task\n~ hourly-sync\nunchanged-task"
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: (out, "", 0))
    token, _ = _session_for("viewer")  # diff is read-only
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "cron", "command": "diff", "workspace": "dev"},
    )
    assert r.status_code == 200
    diff = r.json()["cron_diff"]
    assert diff["added"] == ["nightly-build"]
    assert diff["missing"] == ["stale-task"]
    assert diff["changed"] == ["hourly-sync"]


# --- redacted RYG diagnostics (任务 9.3/9.4, 场景 56-62) ----------------------


def test_env_doctor_returns_ryg_and_masks_secrets(client, monkeypatch):
    out = "GREEN: python ok\nYELLOW: cache stale\nRED: API_TOKEN=supersecret missing scope"
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: (out, "", 0))
    token, _ = _session_for("viewer")  # doctor is read-only
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={"series": "env", "command": "env-doctor", "workspace": "dev"},
    )
    assert r.status_code == 200
    diag = r.json()["diagnostics"]
    levels = {d["level"] for d in diag}
    assert levels == {"green", "yellow", "red"}
    # the sensitive value must not appear in the structured diagnostics or persisted logs
    assert "supersecret" not in r.text
    tid = r.json()["task_id"]
    logs = client.get(f"/admin/askit/tasks/{tid}", headers=_hdr(token)).json()["logs"]
    assert all("supersecret" not in log["line"] for log in logs)


# --- provenance / drift linkage + decompile + PR link (任务 3.3/3.4, 8.x) -----


def test_override_sync_marks_drift_on_managed_agent(client):
    agent_state.set_provenance("ops-bot", "managed")
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={
            "series": "override",
            "command": "sync",
            "workspace": "dev",
            "params": {"agent": "ops-bot"},
        },
    )
    assert r.status_code == 200
    assert agent_state.get_state("ops-bot")["drift"] == 1


def test_promote_clears_drift_and_returns_pr_link(client, monkeypatch):
    agent_state.set_provenance("ops-bot", "managed")
    agent_state.mark_drift("ops-bot")
    out = "promoted override\nPR: https://git.example.com/fleet/pr/42"
    monkeypatch.setattr(runner, "run_subprocess", lambda argv: (out, "", 0))
    token, uid = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),
        json={
            "series": "override",
            "command": "promote",
            "workspace": "dev",
            "params": {"agent": "ops-bot"},
        },
    )
    assert r.status_code == 200
    assert r.json()["pr_url"] == "https://git.example.com/fleet/pr/42"
    assert agent_state.get_state("ops-bot")["drift"] == 0
    entries = audit.search_audit(action="askit.override.promote")
    assert any(e["detail"].get("pr_url") == "https://git.example.com/fleet/pr/42" for e in entries)


def test_discard_keeps_drift_until_deploy_restores(client):
    agent_state.set_provenance("ops-bot", "managed")
    agent_state.mark_drift("ops-bot")
    token, _ = _session_for("admin")
    client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={
            "series": "override",
            "command": "discard",
            "workspace": "dev",
            "params": {"agent": "ops-bot"},
        },
    )
    assert agent_state.get_state("ops-bot")["drift"] == 1  # discard alone does not clear
    client.post(
        "/admin/askit/run",
        headers=_hdr(token, confirm=True),
        json={
            "series": "deploy",
            "command": "deploy",
            "workspace": "dev",
            "params": {"agent": "ops-bot"},
        },
    )
    assert agent_state.get_state("ops-bot")["drift"] == 0  # spec deploy restores + clears


def test_decompile_flips_provenance_keeping_identity(client):
    agent_state.set_provenance("tmp-bot", "adhoc")  # ad-hoc agent
    token, _ = _session_for("admin")
    r = client.post(
        "/admin/askit/run",
        headers=_hdr(token),
        json={
            "series": "override",
            "command": "decompile",
            "workspace": "dev",
            "params": {"agent": "tmp-bot"},
        },
    )
    assert r.status_code == 200
    # flag flip only — same name row, no rebuild; provenance becomes managed
    assert agent_state.get_state("tmp-bot")["provenance"] == "managed"
