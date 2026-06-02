"""Tests for provider_admin_api (/admin/providers). Covers platform.md scenarios 115-120.

model-router / observability seams are monkeypatched so the tests exercise the
management behaviour (CRUD, masking, route orchestration, role guards, audit).
"""

from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.provider_admin_api as api
import fleetent.provider_admin_store as store
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
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


def _add(client, token, pid="p", **kw):
    body = {
        "id": pid,
        "base_url": "https://api.openai.com/v1/",
        "model": "gpt-5.5",
        "api_key": "sk-secret",
        **kw,
    }
    return client.post("/admin/providers", headers=_hdr(token), json=body)


# --- auth / masking -----------------------------------------------------------


def test_no_auth_401(client):
    assert client.get("/admin/providers").status_code == 401


def test_viewer_cannot_write(client):  # 场景 120
    token, _ = _session_for("viewer")
    assert _add(client, token).status_code == 403


def test_add_provider_masks_key_in_response(client):
    token, _ = _session_for("admin")
    r = _add(client, token)
    assert r.status_code == 200
    assert r.json()["api_key"] == "****"  # never plaintext
    assert r.json()["api_key_set"] is True


def test_list_masks_key(client):
    token, _ = _session_for("admin")
    _add(client, token)
    viewer, _ = _session_for("viewer")
    r = client.get("/admin/providers", headers=_hdr(viewer))
    assert r.json()[0]["api_key"] == "****"


# --- connectivity test (场景 115) --------------------------------------------


def test_connectivity_test_reachable(client, monkeypatch):
    monkeypatch.setattr(
        api,
        "router_connectivity_test",
        lambda p: {"reachable": True, "latency_ms": 42, "model": p["model"]},
    )
    token, _ = _session_for("admin")
    _add(client, token)
    r = client.post("/admin/providers/p/connectivity-test", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["reachable"] is True
    assert r.json()["latency_ms"] == 42
    assert r.json()["model"] == "gpt-5.5"


def test_connectivity_test_viewer_forbidden(client):
    token, _ = _session_for("admin")
    _add(client, token)
    viewer, _ = _session_for("viewer")
    assert (
        client.post("/admin/providers/p/connectivity-test", headers=_hdr(viewer)).status_code == 403
    )


# --- route orchestration + fallback order (场景 116) -------------------------


def test_route_order_set_and_reorder(client):
    token, _ = _session_for("admin")
    _add(client, token, pid="a")
    _add(client, token, pid="b")
    client.put(
        "/admin/providers/routes/code", headers=_hdr(token), json={"provider_ids": ["a", "b"]}
    )
    assert store.get_route_providers("code") == ["a", "b"]
    client.put(
        "/admin/providers/routes/code", headers=_hdr(token), json={"provider_ids": ["b", "a"]}
    )
    assert store.get_route_providers("code") == ["b", "a"]
    assert any(a["action"] == "provider.route_set" for a in audit.search_audit())


def test_route_viewer_cannot_reorder(client):
    token, _ = _session_for("viewer")
    r = client.put(
        "/admin/providers/routes/code", headers=_hdr(token), json={"provider_ids": ["a"]}
    )
    assert r.status_code == 403


# --- unknown task_type falls back to default (场景 117) ----------------------


def test_unconfigured_task_type_preview_falls_back(client):
    token, _ = _session_for("admin")
    r = client.get("/admin/providers/routes/never/preview", headers=_hdr(token))
    assert r.json()["chain"] == []
    assert r.json()["falls_back_to"] == "default"


def test_configured_task_type_preview_chain(client):
    token, _ = _session_for("admin")
    _add(client, token, pid="a")
    _add(client, token, pid="b")
    client.put(
        "/admin/providers/routes/code", headers=_hdr(token), json={"provider_ids": ["a", "b"]}
    )
    r = client.get("/admin/providers/routes/code/preview", headers=_hdr(token))
    assert r.json()["chain"] == ["a", "b"]
    assert r.json()["falls_back_to"] is None


# --- pricing: unset shows 未配置, not 0 (场景 118) ---------------------------


def test_unset_pricing_shows_unconfigured(client, monkeypatch):
    monkeypatch.setattr(
        api, "provider_observability", lambda pid: {"provider_id": pid, "calls": 5, "tokens": 100}
    )
    token, _ = _session_for("admin")
    _add(client, token)
    r = client.get("/admin/providers/p/observability", headers=_hdr(token))
    assert r.json()["input_price_per_1k"] == "未配置"


def test_explicit_zero_pricing_distinct_from_unset(client):
    token, _ = _session_for("admin")
    _add(client, token)
    r = client.put(
        "/admin/providers/p/pricing",
        headers=_hdr(token),
        json={"input_price_per_1k": 0.0, "output_price_per_1k": 0.0},
    )
    assert r.json()["input_price_per_1k"] == 0.0  # configured 0, not 未配置


def test_set_pricing_then_observability_uses_it(client, monkeypatch):
    monkeypatch.setattr(api, "provider_observability", lambda pid: {"provider_id": pid})
    token, _ = _session_for("admin")
    _add(client, token)
    client.put(
        "/admin/providers/p/pricing",
        headers=_hdr(token),
        json={"input_price_per_1k": 1.5, "output_price_per_1k": 3.0},
    )
    r = client.get("/admin/providers/p/observability", headers=_hdr(token))
    assert r.json()["input_price_per_1k"] == 1.5


# --- delete removes from routes + audit (场景 119) ---------------------------


def test_delete_provider_removes_from_routes_and_audits(client):
    token, _ = _session_for("admin")
    _add(client, token, pid="a")
    _add(client, token, pid="b")
    client.put(
        "/admin/providers/routes/default", headers=_hdr(token), json={"provider_ids": ["a", "b"]}
    )
    r = client.delete("/admin/providers/a", headers=_hdr(token))
    assert r.status_code == 200
    assert store.get_route_providers("default") == ["b"]
    assert any(a["action"] == "provider.delete" for a in audit.search_audit())


def test_edit_blank_key_keeps_secret(client):
    token, _ = _session_for("admin")
    _add(client, token)
    client.put("/admin/providers/p", headers=_hdr(token), json={"base_url": "https://new/"})
    assert store.get_provider("p")["api_key"] == "sk-secret"  # unchanged in store
    r = client.get("/admin/providers", headers=_hdr(token))
    assert r.json()[0]["base_url"] == "https://new/"
    assert r.json()[0]["api_key"] == "****"
