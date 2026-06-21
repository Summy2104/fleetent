from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import fleetent.server as server
from tests.integration.test_migrations import apply_migrations


@pytest.fixture()
def client(tmp_path, monkeypatch):
    dist_dir = tmp_path / 'frontend-dist'
    dist_dir.mkdir(parents=True)
    (dist_dir / 'index.html').write_text(
        '<!doctype html><html><body><div id="root">frontend-shell</div></body></html>',
        encoding='utf-8',
    )
    (dist_dir / 'assets').mkdir()
    (dist_dir / 'assets' / 'app.js').write_text('console.log("asset");', encoding='utf-8')

    monkeypatch.setenv('DATABASE_URL', f"sqlite:///{tmp_path / 'users.db'}")
    apply_migrations(tmp_path / 'users.db')
    monkeypatch.setattr(server, 'ADMIN_UI_DIST_DIR', dist_dir)

    return TestClient(server.app)


def test_admin_ui_spa_and_legacy_routes_do_not_shadow_api(client: TestClient) -> None:
    root = client.get('/admin/ui')
    assert root.status_code == 200
    assert 'frontend-shell' in root.text

    deep_link = client.get('/admin/ui/agents')
    assert deep_link.status_code == 200
    assert 'frontend-shell' in deep_link.text

    legacy = client.get('/admin/ui-legacy')
    assert legacy.status_code == 200
    assert 'data-tab="users"' in legacy.text

    api = client.get('/admin/me')
    assert api.status_code == 401
    assert 'frontend-shell' not in api.text
