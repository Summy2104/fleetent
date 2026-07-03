"""Unit tests for pool_sync (external git → pool inbound sync).

All collaborators (git_source_store / pool_git / skill_admin_store / secret_store /
registry / audit) are mocked — no real DB, no real git, no network. Covers: is_sync_due
boundaries, skip-when-unconfigured, fetch-failure bulkhead, audit gate (severe →
quarantine, no version), deleted-skill archival, and the unchanged-sha short circuit.
"""

from __future__ import annotations

from pathlib import Path
from unittest import mock

from fleetent.platform.skill_management import pool_sync
from fleetent.skills.audit import Hit

_NOW = "2026-06-30T00:06:00+00:00"


# --- is_sync_due (pure) -------------------------------------------------------


def test_is_sync_due_none_config() -> None:
    assert pool_sync.is_sync_due(None, now_iso=_NOW) is False


def test_is_sync_due_disabled() -> None:
    cfg = {"enabled": 0, "sync_interval_seconds": 300, "last_sync_at": None}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is False


def test_is_sync_due_null_interval_follows_scheduler_tick() -> None:
    # NULL = operator never set a per-source interval. It must NOT silently disable scheduled
    # sync; instead every sweep is "due" (the cheap ls-remote probe short-circuits an unchanged
    # tip), so the pool still tracks the remote at the scheduler's cadence.
    cfg = {"enabled": 1, "sync_interval_seconds": None, "last_sync_at": _NOW}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is True


def test_is_sync_due_explicit_zero_disables() -> None:
    # Explicit 0 is a deliberate "never on a timer" (distinct from NULL/unset).
    cfg = {"enabled": 1, "sync_interval_seconds": 0, "last_sync_at": None}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is False


def test_is_sync_due_never_synced() -> None:
    cfg = {"enabled": 1, "sync_interval_seconds": 300, "last_sync_at": None}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is True


def test_is_sync_due_elapsed() -> None:
    cfg = {"enabled": 1, "sync_interval_seconds": 300, "last_sync_at": "2026-06-30T00:00:00+00:00"}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is True  # 360s >= 300


def test_is_sync_due_not_elapsed() -> None:
    cfg = {"enabled": 1, "sync_interval_seconds": 300, "last_sync_at": "2026-06-30T00:04:00+00:00"}
    assert pool_sync.is_sync_due(cfg, now_iso=_NOW) is False  # 120s < 300


# --- sync_external_git --------------------------------------------------------


def test_sync_skips_when_not_configured(monkeypatch) -> None:
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: None)
    result = pool_sync.sync_external_git()
    assert result.get("skipped") is True


def test_sync_bulkheads_fetch_failure(monkeypatch) -> None:
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": None,
    }
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: cfg)
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    monkeypatch.setattr(pool_sync.pool_git, "init_pool_with_remote", lambda *a, **k: None)
    # Probe returns a differing tip so the flow proceeds to the (failing) fetch.
    monkeypatch.setattr(pool_sync.pool_git, "get_remote_head", lambda *a, **k: "newsha")

    def _raise(*a, **k):
        raise RuntimeError("net down")

    monkeypatch.setattr(pool_sync.pool_git, "fetch_remote", _raise)
    rec = mock.Mock()
    monkeypatch.setattr(pool_sync.git_source_store, "record_sync", rec)

    result = pool_sync.sync_external_git()  # must not raise

    assert "error" in result
    rec.assert_called_once()
    assert rec.call_args.kwargs["error"] == "net down"


def test_sync_skips_fetch_when_remote_tip_unchanged(monkeypatch) -> None:
    """The refs-only probe short-circuits a full fetch when the branch tip is unchanged."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": "abc",
    }
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: cfg)
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    monkeypatch.setattr(pool_sync.pool_git, "init_pool_with_remote", lambda *a, **k: None)
    monkeypatch.setattr(pool_sync.pool_git, "get_remote_head", lambda *a, **k: "abc")
    fetch = mock.Mock()
    reset = mock.Mock()
    monkeypatch.setattr(pool_sync.pool_git, "fetch_remote", fetch)
    monkeypatch.setattr(pool_sync.pool_git, "reset_pool_to", reset)
    monkeypatch.setattr(pool_sync.git_source_store, "record_sync", mock.Mock())

    result = pool_sync.sync_external_git(trigger="scheduled")

    assert result.get("changed") is False
    fetch.assert_not_called()  # the whole point: no expensive fetch when tip is unchanged
    reset.assert_not_called()


def test_manual_sync_skips_fetch_but_realigns_when_tip_unchanged(monkeypatch) -> None:
    """A manual trigger with an unchanged tip still re-aligns status (drift recovery) but
    must not fetch — the fetch is the slow part we are avoiding."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": "abc",
    }
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: cfg)
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    monkeypatch.setattr(pool_sync.pool_git, "init_pool_with_remote", lambda *a, **k: None)
    monkeypatch.setattr(pool_sync.pool_git, "get_remote_head", lambda *a, **k: "abc")
    fetch = mock.Mock()
    realign = mock.Mock()
    monkeypatch.setattr(pool_sync.pool_git, "fetch_remote", fetch)
    monkeypatch.setattr(pool_sync, "_realign_status_only", realign)
    monkeypatch.setattr(pool_sync.skill_registry, "reload", mock.Mock())
    monkeypatch.setattr(pool_sync.git_source_store, "record_sync", mock.Mock())

    result = pool_sync.sync_external_git(trigger="manual")

    assert result.get("changed") is False
    assert result.get("reconciled") is True
    fetch.assert_not_called()
    realign.assert_called_once()


def test_probe_failure_falls_back_to_full_fetch(monkeypatch) -> None:
    """If the ls-remote probe raises, sync must still fall through to a real fetch."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": "abc",
    }
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: cfg)
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    monkeypatch.setattr(pool_sync.pool_git, "init_pool_with_remote", lambda *a, **k: None)

    def _probe_boom(*a, **k):
        raise RuntimeError("ls-remote unreachable")

    monkeypatch.setattr(pool_sync.pool_git, "get_remote_head", _probe_boom)
    fetch = mock.Mock(return_value="abc")  # fetch confirms unchanged
    monkeypatch.setattr(pool_sync.pool_git, "fetch_remote", fetch)
    monkeypatch.setattr(pool_sync.pool_git, "reset_pool_to", mock.Mock())
    monkeypatch.setattr(pool_sync.git_source_store, "record_sync", mock.Mock())

    result = pool_sync.sync_external_git(trigger="scheduled")

    assert result.get("changed") is False
    fetch.assert_called_once()  # probe failed -> real fetch happened


# --- git-root / scan-root split (R1) ------------------------------------------


def _stub_do_sync_collaborators(monkeypatch, cfg: dict) -> dict[str, mock.Mock]:
    """Wire _do_sync so it runs the changed path once, returning the git-op mocks."""
    monkeypatch.setattr(pool_sync.git_source_store, "get_config", lambda: cfg)
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool/skills"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    monkeypatch.setattr(pool_sync.git_source_store, "record_sync", mock.Mock())
    mocks = {
        "init_pool_with_remote": mock.Mock(),
        "reset_pool_to": mock.Mock(),
        "commit_pool": mock.Mock(return_value=None),
        "list_pool_skills": mock.Mock(return_value=[]),
        # Probe returns None (unavailable) so the flow falls through to a real fetch;
        # fetch's sha differs from last_synced_commit -> the "changed" path.
        "get_remote_head": mock.Mock(return_value=None),
        "fetch_remote": mock.Mock(return_value="newsha"),
    }
    for name, m in mocks.items():
        monkeypatch.setattr(pool_sync.pool_git, name, m)
    monkeypatch.setattr(pool_sync.skill_admin_store, "ensure_catalog_entries", mock.Mock())
    monkeypatch.setattr(
        pool_sync.skill_admin_store, "list_states", lambda include_archived=False: []
    )
    monkeypatch.setattr(pool_sync.skill_registry, "materialize_builtin_skills", mock.Mock())
    return mocks


def test_do_sync_passes_git_root_to_git_ops_with_subdir(monkeypatch) -> None:
    """With skills_subdir set, fetch/reset/init operate on the git root (not scan root)."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": None,
        "skills_subdir": "skills",
    }
    mocks = _stub_do_sync_collaborators(monkeypatch, cfg)
    sentinel = Path("/tmp/pool")  # what resolve_git_root would produce for scan=/tmp/pool/skills
    monkeypatch.setattr(pool_sync.pool_git, "resolve_git_root", lambda scan, sub: sentinel)

    result = pool_sync.sync_external_git()

    assert result.get("changed") is True
    assert mocks["init_pool_with_remote"].call_args.args[0] == sentinel
    assert mocks["fetch_remote"].call_args.args[0] == sentinel
    assert mocks["reset_pool_to"].call_args.args[0] == sentinel
    # commit_pool (builtin re-seed) also opens a Repo -> git root
    assert mocks["commit_pool"].call_args.args[0] == sentinel


def test_do_sync_passes_subdir_to_builtin_reseed_commit(monkeypatch) -> None:
    """The builtin re-seed commit_pool call must also scope staging to the subdir.

    Without ``subdir``, ``commit_pool``'s skill_name=None branch stages the entire
    git root — which equals FLEETENT_HOME itself when skills_subdir causes git_root
    == scan_root's parent, silently committing management.db/.env/node/logs/tenants
    into the pool repo.
    """
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": None,
        "skills_subdir": "skills",
    }
    mocks = _stub_do_sync_collaborators(monkeypatch, cfg)
    sentinel = Path("/tmp/pool")
    monkeypatch.setattr(pool_sync.pool_git, "resolve_git_root", lambda scan, sub: sentinel)

    pool_sync.sync_external_git()

    assert mocks["commit_pool"].call_args.kwargs.get("subdir") == "skills"


def test_do_sync_passes_subdir_to_version_and_content(monkeypatch) -> None:
    """pool_version_for_skill / pool_content_at get git root + subdir='skills'."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": None,
        "skills_subdir": "skills",
    }
    mocks = _stub_do_sync_collaborators(monkeypatch, cfg)
    mocks["list_pool_skills"].return_value = ["clean"]
    sentinel = Path("/tmp/pool")
    monkeypatch.setattr(pool_sync.pool_git, "resolve_git_root", lambda scan, sub: sentinel)
    content = mock.Mock(return_value="clean body")
    version = mock.Mock(return_value="sha_clean")
    monkeypatch.setattr(pool_sync.pool_git, "pool_content_at", content)
    monkeypatch.setattr(pool_sync.pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(pool_sync.skill_audit, "audit", lambda c, d: [])
    monkeypatch.setattr(pool_sync.skill_audit, "has_severe", lambda hits: False)
    for name in ("set_status", "set_current_version", "set_audit_result", "set_source"):
        monkeypatch.setattr(pool_sync.skill_admin_store, name, mock.Mock())

    pool_sync.sync_external_git()

    # list is scan-root scoped; content/version are git-root + subdir scoped
    assert mocks["list_pool_skills"].call_args.args[0] == Path("/tmp/pool/skills")
    assert content.call_args.args[0] == sentinel
    assert content.call_args.kwargs["subdir"] == "skills"
    assert version.call_args.args[0] == sentinel
    assert version.call_args.kwargs["subdir"] == "skills"


def test_do_sync_no_subdir_degenerates_to_scan_root(monkeypatch) -> None:
    """Without skills_subdir, git root == scan root and subdir='' (backward compat)."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "last_synced_commit": None,
    }
    mocks = _stub_do_sync_collaborators(monkeypatch, cfg)
    mocks["list_pool_skills"].return_value = ["clean"]
    # Let the real resolve_git_root run: empty subdir -> identity.
    content = mock.Mock(return_value="clean body")
    version = mock.Mock(return_value="sha_clean")
    monkeypatch.setattr(pool_sync.pool_git, "pool_content_at", content)
    monkeypatch.setattr(pool_sync.pool_git, "pool_version_for_skill", version)
    monkeypatch.setattr(pool_sync.skill_audit, "audit", lambda c, d: [])
    monkeypatch.setattr(pool_sync.skill_audit, "has_severe", lambda hits: False)
    for name in ("set_status", "set_current_version", "set_audit_result", "set_source"):
        monkeypatch.setattr(pool_sync.skill_admin_store, name, mock.Mock())

    scan_root = Path("/tmp/pool/skills")  # _pool_dir() stub in helper
    pool_sync.sync_external_git()

    assert mocks["init_pool_with_remote"].call_args.args[0] == scan_root
    assert mocks["reset_pool_to"].call_args.args[0] == scan_root
    assert content.call_args.args[0] == scan_root
    assert content.call_args.kwargs["subdir"] == ""
    assert version.call_args.args[0] == scan_root
    assert version.call_args.kwargs["subdir"] == ""


def test_align_pool_to_remote_uses_git_root_with_subdir(monkeypatch) -> None:
    """align_pool_to_remote fetch/reset/init operate on the git root too."""
    cfg = {
        "enabled": 1,
        "remote_url": "https://git/x",
        "branch": "main",
        "skills_subdir": "skills",
    }
    monkeypatch.setattr(pool_sync, "_pool_dir", lambda: Path("/tmp/pool/skills"))
    monkeypatch.setattr(pool_sync, "_secret", lambda env: None)
    sentinel = Path("/tmp/pool")
    monkeypatch.setattr(pool_sync.pool_git, "resolve_git_root", lambda scan, sub: sentinel)
    init = mock.Mock()
    reset = mock.Mock()
    monkeypatch.setattr(pool_sync.pool_git, "init_pool_with_remote", init)
    monkeypatch.setattr(pool_sync.pool_git, "reset_pool_to", reset)
    fetch = mock.Mock(return_value="sha")
    monkeypatch.setattr(pool_sync.pool_git, "fetch_remote", fetch)

    result = pool_sync.align_pool_to_remote(cfg)

    assert result == "sha"
    assert init.call_args.args[0] == sentinel
    assert fetch.call_args.args[0] == sentinel
    assert reset.call_args.args[0] == sentinel


# --- _reconcile_catalog_after_sync (audit gate + archival) --------------------


def _stub_reconcile_store(monkeypatch) -> dict[str, mock.Mock]:
    mocks = {
        "ensure_catalog_entries": mock.Mock(),
        "set_status": mock.Mock(),
        "set_current_version": mock.Mock(),
        "set_audit_result": mock.Mock(),
        "set_source": mock.Mock(),
    }
    for name, m in mocks.items():
        monkeypatch.setattr(pool_sync.skill_admin_store, name, m)
    monkeypatch.setattr(
        pool_sync.skill_audit, "has_severe", lambda hits: any(h.severity == "severe" for h in hits)
    )
    return mocks


def test_reconcile_quarantines_severe_and_versions_clean(monkeypatch) -> None:
    monkeypatch.setattr(pool_sync.pool_git, "list_pool_skills", lambda p: ["clean", "evil"])
    monkeypatch.setattr(
        pool_sync.pool_git,
        "pool_content_at",
        lambda p, n, r, *, subdir="": "evil body" if n == "evil" else "clean body",
    )
    monkeypatch.setattr(
        pool_sync.pool_git, "pool_version_for_skill", lambda p, n, *, subdir="": "sha_" + n
    )
    monkeypatch.setattr(
        pool_sync.skill_admin_store, "list_states", lambda include_archived=False: []
    )
    monkeypatch.setattr(
        pool_sync.skill_audit,
        "audit",
        lambda content, desc: (
            [Hit(rule_id="inj", severity="severe", field="content", match="m")]
            if "evil" in content
            else []
        ),
    )
    m = _stub_reconcile_store(monkeypatch)

    pool_sync._reconcile_catalog_after_sync(Path("/tmp/pool"), Path("/tmp/pool"), "")

    m["set_status"].assert_any_call("evil", "quarantined")
    m["set_status"].assert_any_call("clean", "active")
    versioned = [c.args[0] for c in m["set_current_version"].call_args_list]
    assert "clean" in versioned
    assert "evil" not in versioned  # quarantined skill not versioned (not distributed)


def test_reconcile_archives_deleted_skill(monkeypatch) -> None:
    monkeypatch.setattr(pool_sync.pool_git, "list_pool_skills", lambda p: ["kept"])
    monkeypatch.setattr(pool_sync.pool_git, "pool_content_at", lambda p, n, r, *, subdir="": "ok")
    monkeypatch.setattr(
        pool_sync.pool_git, "pool_version_for_skill", lambda p, n, *, subdir="": "sha"
    )
    monkeypatch.setattr(pool_sync.skill_audit, "audit", lambda content, desc: [])
    monkeypatch.setattr(
        pool_sync.skill_admin_store,
        "list_states",
        lambda include_archived=False: [
            {"skill_name": "kept", "status": "active"},
            {"skill_name": "gone", "status": "active"},
        ],
    )
    m = _stub_reconcile_store(monkeypatch)

    pool_sync._reconcile_catalog_after_sync(Path("/tmp/pool"), Path("/tmp/pool"), "")

    m["set_status"].assert_any_call("gone", "archived")  # not in pool → soft-deleted
