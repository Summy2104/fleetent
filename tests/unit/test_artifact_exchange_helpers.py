from __future__ import annotations

import errno
import os
from pathlib import Path

from fleetent import artifact_exchange


def test_view_dir_returns_none_without_views_root_or_scope_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(artifact_exchange, "_views_root", None)
    assert artifact_exchange.view_dir("scope-1") is None

    monkeypatch.setattr(artifact_exchange, "_views_root", tmp_path)
    assert artifact_exchange.view_dir(None) is None


def test_view_dir_creates_scope_directory(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(artifact_exchange, "_views_root", tmp_path)

    view = artifact_exchange.view_dir("scope-1")

    assert view == tmp_path / "scope-1"
    assert view is not None and view.is_dir()


def test_snapshot_products_skips_dotfiles_tmp_and_missing_root(tmp_path) -> None:
    root = tmp_path / "products"
    root.mkdir()
    (root / "keep.txt").write_text("ok", encoding="utf-8")
    (root / "skip.tmp").write_text("tmp", encoding="utf-8")
    hidden_dir = root / ".cache"
    hidden_dir.mkdir()
    (hidden_dir / "secret.txt").write_text("x", encoding="utf-8")
    hidden_file = root / ".env"
    hidden_file.write_text("x", encoding="utf-8")

    snap = artifact_exchange.snapshot_products(root)

    assert list(snap) == ["keep.txt"]
    assert artifact_exchange.snapshot_products(root / "missing") == {}


def test_diff_register_requires_scope_key(tmp_path, monkeypatch) -> None:
    root = tmp_path / "products"
    root.mkdir()
    (root / "a.txt").write_text("a", encoding="utf-8")
    called: list[dict[str, object]] = []
    monkeypatch.setattr(artifact_exchange, "register", lambda **kwargs: called.append(kwargs))

    changed = artifact_exchange.diff_register("gd", root, {}, None)

    assert changed == []
    assert called == []


def test_diff_register_registers_new_and_changed_files(tmp_path, monkeypatch) -> None:
    root = tmp_path / "products"
    root.mkdir()
    a = root / "a.txt"
    b = root / "b.txt"
    a.write_text("old", encoding="utf-8")
    b.write_text("new", encoding="utf-8")
    before = artifact_exchange.snapshot_products(root)
    a.write_text("updated", encoding="utf-8")

    called: list[dict[str, object]] = []
    monkeypatch.setattr(artifact_exchange, "register", lambda **kwargs: called.append(kwargs))

    changed = artifact_exchange.diff_register(
        "gd",
        root,
        before,
        "scope-1",
        session_id="session-1",
        user_id="user-1",
    )

    assert sorted(changed) == ["a.txt"]
    assert called == [
        {
            "server_id": "gd",
            "rel_path": "a.txt",
            "scope_key": "scope-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "filename": "a.txt",
            "size": os.path.getsize(a),
        }
    ]


def test_rewrite_and_register_is_noop_without_root_or_scope(monkeypatch) -> None:
    monkeypatch.setattr(artifact_exchange, "_server_roots", {})
    text = "/tmp/anywhere/report.txt"

    assert artifact_exchange.rewrite_and_register("gd", text, "scope-1") == text

    monkeypatch.setattr(artifact_exchange, "_server_roots", {"gd": Path("/tmp/exchange/gd")})
    assert artifact_exchange.rewrite_and_register("gd", text, None) == text


def test_rewrite_and_register_rewrites_each_in_root_path_once(tmp_path, monkeypatch) -> None:
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    report = root / "reports" / "daily.txt"
    report.parent.mkdir()
    report.write_text("ok", encoding="utf-8")

    monkeypatch.setattr(artifact_exchange, "_server_roots", {"gd": root})
    registered: list[dict[str, object]] = []
    monkeypatch.setattr(artifact_exchange, "register", lambda **kwargs: registered.append(kwargs))

    text = f"first={report} second={report} outside={tmp_path / 'other.txt'}"
    rewritten = artifact_exchange.rewrite_and_register(
        "gd",
        text,
        "scope-1",
        session_id="session-1",
        user_id="user-1",
    )

    assert rewritten.count("/exchange/gd/reports/daily.txt") == 2
    assert str(tmp_path / "other.txt") in rewritten
    assert registered == [
        {
            "server_id": "gd",
            "rel_path": "reports/daily.txt",
            "scope_key": "scope-1",
            "session_id": "session-1",
            "user_id": "user-1",
            "filename": "daily.txt",
            "size": os.path.getsize(report),
        }
    ]


def test_link_into_view_marks_server_staging_degraded_on_exdev(tmp_path, monkeypatch) -> None:
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("ok", encoding="utf-8")
    views = tmp_path / "views"

    monkeypatch.setattr(artifact_exchange, "_views_root", views)
    monkeypatch.setattr(artifact_exchange, "_server_roots", {"gd": root})
    monkeypatch.setattr(artifact_exchange, "_staging_degraded_servers", set())

    def boom(src: str, dst: str) -> None:
        raise OSError(errno.EXDEV, "cross-device link", src, dst)

    monkeypatch.setattr(artifact_exchange.os, "link", boom)

    artifact_exchange._link_into_view("gd", "a.txt", "scope-1")  # noqa: SLF001

    assert "gd" in artifact_exchange._staging_degraded_servers  # noqa: SLF001
