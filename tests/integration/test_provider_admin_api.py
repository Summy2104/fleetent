"""Tests for provider_admin_api (/admin/providers). Covers platform.md scenarios 115-120.

model-router / observability seams are monkeypatched so the tests exercise the
management behaviour (CRUD, masking, route orchestration, role guards, audit).
"""

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import fleetent.auth as auth
import fleetent.governance.audit_log as audit
import fleetent.platform.model_provider_management.provider_admin_api as api
import fleetent.platform.model_provider_management.provider_admin_store as store
import fleetent.user_store as user_store
from fleetent.db import create_database
from tests.integration._migration_template import apply_migrations


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    """Module-scoped client for auth/read-only tests.

    Patches store._database directly to avoid conflicts with the autouse
    _isolate_database_url conftest fixture that deletes DATABASE_URL per test.
    """
    mp = pytest.MonkeyPatch()
    tmp_path = tmp_path_factory.mktemp("db_ro")
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    db_instance = create_database(f"sqlite:///{db_path}")
    mp.setattr(user_store, "_db", lambda: db_instance)
    mp.setattr(store, "_database", lambda: db_instance)
    mp.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    app = FastAPI()
    app.include_router(api.router)
    yield TestClient(app, raise_server_exceptions=True)
    mp.undo()


@pytest.fixture
def fresh_client(tmp_path, monkeypatch):
    """Function-scoped client for write tests that need a clean DB per test.

    Patches store._database directly (same reason as module client above).
    """
    db_path = tmp_path / "users.db"
    apply_migrations(db_path)
    db_instance = create_database(f"sqlite:///{db_path}")
    monkeypatch.setattr(user_store, "_db", lambda: db_instance)
    monkeypatch.setattr(store, "_database", lambda: db_instance)
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    app = FastAPI()
    app.include_router(api.router)
    return TestClient(app, raise_server_exceptions=True)


def _session_for(role: str) -> tuple[str, str]:
    u, _ = user_store.create_user(f"{role}-user")
    user_store.set_role(u.id, role)
    return auth.create_session(u.id), u.id


def _hdr(token: str) -> dict:
    return {"Authorization": f"Session {token}"}


_LEGACY_ROUTES_PATH = "/admin/providers" + "/routes"


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


def test_add_provider_masks_key_in_response(fresh_client):
    token, _ = _session_for("admin")
    r = _add(fresh_client, token)
    assert r.status_code == 200
    assert r.json()["api_key"] == "****"  # never plaintext
    assert r.json()["api_key_set"] is True


def test_inline_key_auto_derives_env_name(fresh_client):
    # value mode: type the key, the platform names the env var (no api_key_env field)
    token, _ = _session_for("admin")
    r = _add(fresh_client, token, pid="fast-claude")
    assert r.status_code == 200, r.text
    assert r.json()["api_key_env"] == "FLEETENT_MODEL_FAST_CLAUDE_API_KEY"
    assert r.json()["api_key_set"] is True


def test_explicit_env_reference_preserved(fresh_client):
    # reference mode: an explicit env name is kept as-is, not auto-derived
    token, _ = _session_for("admin")
    body = {
        "id": "ref",
        "base_url": "https://api.openai.com/v1/",
        "model": "gpt-5.5",
        "api_key_env": "MY_TEAM_KEY",
    }
    r = fresh_client.post("/admin/providers", headers=_hdr(token), json=body)
    assert r.status_code == 200, r.text
    assert r.json()["api_key_env"] == "MY_TEAM_KEY"
    assert r.json()["api_key_set"] is False


def test_add_provider_vendor_protocol_env_params_roundtrip(fresh_client):
    token, _ = _session_for("admin")
    r = _add(
        fresh_client,
        token,
        pid="fast",
        provider="anthropic",
        protocol="openai_chat",
        api_key_env="FLEETENT_MODEL_FAST_API_KEY",
        max_tokens=2048,
        params={"temperature": 0.3, "top_p": 0.9},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["provider"] == "anthropic"
    assert body["protocol"] == "openai_chat"
    assert body["api_key_env"] == "FLEETENT_MODEL_FAST_API_KEY"  # env name, not masked
    assert body["params"] == {"temperature": 0.3, "top_p": 0.9}
    # editing params + protocol persists
    e = fresh_client.put(
        "/admin/providers/fast",
        headers=_hdr(token),
        json={"protocol": "anthropic_messages", "params": {"temperature": 0.1}},
    )
    assert e.status_code == 200, e.text
    got = fresh_client.get("/admin/providers", headers=_hdr(token)).json()
    fast = next(p for p in got if p["id"] == "fast")
    assert fast["protocol"] == "anthropic_messages"
    assert fast["params"] == {"temperature": 0.1}


def test_list_masks_key(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    viewer, _ = _session_for("viewer")
    r = fresh_client.get("/admin/providers", headers=_hdr(viewer))
    assert r.json()[0]["api_key"] == "****"


# --- connectivity test (场景 115) --------------------------------------------


def test_connectivity_test_reachable(fresh_client, monkeypatch):
    monkeypatch.setattr(
        api,
        "router_connectivity_test",
        lambda p: {"reachable": True, "latency_ms": 42, "model": p["model"]},
    )
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    r = fresh_client.post("/admin/providers/p/connectivity-test", headers=_hdr(token))
    assert r.status_code == 200
    assert r.json()["reachable"] is True
    assert r.json()["latency_ms"] == 42
    assert r.json()["model"] == "gpt-5.5"


def test_connectivity_test_viewer_forbidden(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    viewer, _ = _session_for("viewer")
    assert (
        fresh_client.post("/admin/providers/p/connectivity-test", headers=_hdr(viewer)).status_code
        == 403
    )


# --- route endpoints removed, health view retained ---------------------------


def test_routes_endpoints_removed_but_health_remains(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token, pid="a")

    health = fresh_client.get("/admin/providers/health", headers=_hdr(token))
    assert health.status_code == 200
    assert health.json()["providers"] == [{"id": "a", "available": True, "recovers_at": None}]


def test_provider_routes_ui_and_router_entries_removed() -> None:
    paths = {getattr(route, "path", None) for route in api.router.routes}
    assert "/admin/providers/routes" not in paths
    assert "/admin/providers/routes/{task_type}" not in paths
    assert "/admin/providers/routes/{task_type}/preview" not in paths

    admin_html = (
        Path(__file__).parents[2] / "src" / "fleetent" / "static" / "admin.html"
    ).read_text(encoding="utf-8")
    assert '"/providers/routes"' not in admin_html


# --- health probe state view (4.7/4.8) --------------------------------------


def test_health_view_shows_down_provider_and_recovery(fresh_client, monkeypatch):
    monkeypatch.setattr(
        api,
        "router_health_probe",
        lambda: {"a": {"available": False, "recovers_at": "2026-06-02T10:00:00Z"}},
    )
    token, _ = _session_for("admin")
    _add(fresh_client, token, pid="a")
    _add(fresh_client, token, pid="b")
    r = fresh_client.get("/admin/providers/health", headers=_hdr(token))
    body = r.json()
    providers = {p["id"]: p for p in body["providers"]}
    assert providers["a"]["available"] is False
    assert providers["a"]["recovers_at"] == "2026-06-02T10:00:00Z"
    assert providers["b"]["available"] is True  # not in cache → available
    assert providers["b"]["recovers_at"] is None


def test_health_view_viewer_can_read(client):
    token, _ = _session_for("viewer")
    r = client.get("/admin/providers/health", headers=_hdr(token))
    assert r.status_code == 200


# --- pricing: unset shows 未配置, not 0 (场景 118) ---------------------------


def test_unset_pricing_shows_unconfigured(fresh_client, monkeypatch):
    monkeypatch.setattr(
        api, "provider_observability", lambda pid: {"provider_id": pid, "calls": 5, "tokens": 100}
    )
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    r = fresh_client.get("/admin/providers/p/observability", headers=_hdr(token))
    assert r.json()["input_price_per_1k"] == "未配置"


def test_explicit_zero_pricing_distinct_from_unset(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    r = fresh_client.put(
        "/admin/providers/p/pricing",
        headers=_hdr(token),
        json={"input_price_per_1k": 0.0, "output_price_per_1k": 0.0},
    )
    assert r.json()["input_price_per_1k"] == 0.0  # configured 0, not 未配置


def test_set_pricing_then_observability_uses_it(fresh_client, monkeypatch):
    monkeypatch.setattr(api, "provider_observability", lambda pid: {"provider_id": pid})
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    fresh_client.put(
        "/admin/providers/p/pricing",
        headers=_hdr(token),
        json={"input_price_per_1k": 1.5, "output_price_per_1k": 3.0},
    )
    r = fresh_client.get("/admin/providers/p/observability", headers=_hdr(token))
    assert r.json()["input_price_per_1k"] == 1.5


# --- delete audits without legacy route-table cleanup (场景 119) -------------


def test_delete_provider_without_routes_cleanup_and_audits(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token, pid="a")
    r = fresh_client.delete("/admin/providers/a", headers=_hdr(token))
    assert r.status_code == 200
    assert store.get_provider("a") is None
    assert any(a["action"] == "provider.delete" for a in audit.search_audit())


def test_edit_blank_key_keeps_secret(fresh_client):
    token, _ = _session_for("admin")
    _add(fresh_client, token)
    fresh_client.put("/admin/providers/p", headers=_hdr(token), json={"base_url": "https://new/"})
    assert store.get_provider("p")["api_key"] == "sk-secret"  # unchanged in store
    r = fresh_client.get("/admin/providers", headers=_hdr(token))
    assert r.json()[0]["base_url"] == "https://new/"
    assert r.json()[0]["api_key"] == "****"
