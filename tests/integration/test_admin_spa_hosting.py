from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import fleetent.server as server
from tests.integration.test_migrations import apply_migrations


@pytest.fixture()
def client(tmp_path, monkeypatch):
    dist_dir = tmp_path / "frontend-dist"
    dist_dir.mkdir(parents=True)
    (dist_dir / "index.html").write_text(
        '<!doctype html><html><body><div id="root">frontend-shell</div></body></html>',
        encoding="utf-8",
    )
    (dist_dir / "assets").mkdir()
    (dist_dir / "assets" / "app.js").write_text('console.log("asset");', encoding="utf-8")

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    monkeypatch.setattr(server, "ADMIN_UI_DIST_DIR", dist_dir)

    return TestClient(server.app)


def _make_client(tmp_path, monkeypatch, dist_dir: Path | None) -> TestClient:
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / "users.db")
    if dist_dir is None:
        monkeypatch.delenv("FLEETENT_ADMIN_UI_DIST", raising=False)
    else:
        monkeypatch.setenv("FLEETENT_ADMIN_UI_DIST", str(dist_dir))
    return TestClient(server.app)


def test_admin_ui_spa_and_legacy_routes_do_not_shadow_api(client: TestClient) -> None:
    root = client.get("/admin/ui")
    assert root.status_code == 200
    assert "frontend-shell" in root.text

    deep_link = client.get("/admin/ui/agents")
    assert deep_link.status_code == 200
    assert "frontend-shell" in deep_link.text

    legacy = client.get("/admin/ui-legacy")
    assert legacy.status_code == 200
    assert 'data-tab="users"' in legacy.text

    api = client.get("/admin/me")
    assert api.status_code == 401
    assert "frontend-shell" not in api.text


def test_admin_ui_uses_env_override_dist(tmp_path, monkeypatch) -> None:
    dist_dir = tmp_path / "custom-dist"
    dist_dir.mkdir()
    (dist_dir / "index.html").write_text(
        '<!doctype html><html><body><div id="root">env-dist</div></body></html>',
        encoding="utf-8",
    )

    client = _make_client(tmp_path, monkeypatch, dist_dir)

    response = client.get("/admin/ui")

    assert response.status_code == 200
    assert "env-dist" in response.text


def test_admin_ui_returns_503_without_default_or_env_dist(tmp_path, monkeypatch) -> None:
    client = _make_client(tmp_path, monkeypatch, None)
    monkeypatch.setattr(server, "ADMIN_UI_DIST_DIR", tmp_path / "missing-default-dist")

    response = client.get("/admin/ui")

    assert response.status_code == 503
    assert response.json() == {"detail": "admin frontend dist not built"}


def test_admin_ui_returns_503_when_env_override_dist_missing(tmp_path, monkeypatch) -> None:
    missing_dist = tmp_path / "missing-env-dist"
    client = _make_client(tmp_path, monkeypatch, missing_dist)
    monkeypatch.setattr(server, "ADMIN_UI_DIST_DIR", tmp_path / "fallback-dist")

    response = client.get("/admin/ui")

    assert response.status_code == 503
    assert response.json() == {"detail": "admin frontend dist not built"}
