from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.user_store as user_store
from fleetent import vector_store
from fleetent.memory import shared
from fleetent.memory.shared_memory_migrations import MIGRATIONS
from fleetent.server import app
from fleetent.tenant_router import SQLiteTenantBackend, TenantRouter
from tests.integration._migration_template import apply_migrations


class _NullBackend:
    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        del id, vector, namespace

    async def search(self, vector: list[float], namespace: str, limit: int = 10) -> list[Any]:
        del vector, namespace, limit
        return []

    async def delete(self, id: str, namespace: str) -> None:
        del id, namespace

    async def clear_namespace(self, namespace: str) -> None:
        del namespace


def _client(tmp_path, monkeypatch) -> TestClient:
    db_path = tmp_path / "management.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    apply_migrations(db_path)

    router = TenantRouter(SQLiteTenantBackend(data_dir=tmp_path))
    scope = router.tenant_scope("default")
    shared.set_shared_memory_db(scope.open_shared_memory_db(MIGRATIONS), _NullBackend())

    async def _embed_text(text: str) -> list[float]:
        del text
        return [1.0, 0.0]

    monkeypatch.setattr(vector_store, "embed_text", _embed_text)
    return TestClient(app, raise_server_exceptions=True)


def _session_header(role: str) -> dict[str, str]:
    user, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(user.id, role)
    token = auth.create_session(user.id)
    return {"Authorization": f"Session {token}"}


def test_shared_memory_routes_exist(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.get(
        "/admin/memory/shared?scope_type=team&scope_id=eng",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200


def test_list_shared_memory(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    client.post(
        "/admin/memory/shared",
        headers=_session_header("admin"),
        json={
            "scope_type": "team",
            "scope_id": "eng",
            "type": "context",
            "content": "Release notes should stay concise.",
        },
    )

    response = client.get(
        "/admin/memory/shared?scope_type=team&scope_id=eng",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert response.json()[0]["content"] == "Release notes should stay concise."


def test_create_shared_memory(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/memory/shared",
        headers=_session_header("admin"),
        json={
            "scope_type": "team",
            "scope_id": "eng",
            "type": "procedure",
            "content": "Escalate incidents within 10 minutes.",
        },
    )

    assert response.status_code == 201
    assert response.json()["status"] == "active"
    assert response.json()["type"] == "procedure"


def test_update_shared_memory(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/admin/memory/shared",
        headers=_session_header("admin"),
        json={
            "scope_type": "team",
            "scope_id": "eng",
            "type": "context",
            "content": "Old content.",
        },
    )
    item_id = created.json()["id"]

    response = client.patch(
        f"/admin/memory/shared/{item_id}",
        headers=_session_header("admin"),
        json={"content": "New content."},
    )

    assert response.status_code == 200
    assert response.json()["content"] == "New content."


def test_archive_shared_memory(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/admin/memory/shared",
        headers=_session_header("admin"),
        json={
            "scope_type": "tenant",
            "scope_id": "default",
            "type": "context",
            "content": "Archive me.",
        },
    )
    item_id = created.json()["id"]

    response = client.post(
        f"/admin/memory/shared/{item_id}/archive",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert response.json()["status"] == "archived"


def test_archived_excluded_by_default(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)
    created = client.post(
        "/admin/memory/shared",
        headers=_session_header("admin"),
        json={
            "scope_type": "team",
            "scope_id": "eng",
            "type": "context",
            "content": "Archive me.",
        },
    )
    item_id = created.json()["id"]
    client.post(
        f"/admin/memory/shared/{item_id}/archive",
        headers=_session_header("admin"),
    )

    response = client.get(
        "/admin/memory/shared?scope_type=team&scope_id=eng",
        headers=_session_header("admin"),
    )

    assert response.status_code == 200
    assert response.json() == []


def test_non_admin_returns_403(tmp_path, monkeypatch) -> None:
    client = _client(tmp_path, monkeypatch)

    response = client.post(
        "/admin/memory/shared",
        headers=_session_header("viewer"),
        json={
            "scope_type": "team",
            "scope_id": "eng",
            "type": "context",
            "content": "Nope.",
        },
    )

    assert response.status_code == 403
