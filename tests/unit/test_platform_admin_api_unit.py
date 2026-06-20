"""Fast unit coverage for admin API route handlers.

These tests keep route-level authorization, branching, audit calls, and injectable
seam behavior in unit scope. Database/Alembic behavior stays in integration tests.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import HTTPException

from fleetent import server, user_store
from fleetent.platform.chat_management import chat_admin_api
from fleetent.platform.knowledge_base_management import kb_admin_api
from fleetent.platform.model_provider_management import provider_admin_api
from fleetent.platform.skill_management import skill_admin_api
from fleetent.platform.user_management import user_admin_api


def _user(
    role: str = "admin",
    *,
    user_id: str = "admin-1",
    must_reset: int = 0,
    status: str = "active",
) -> user_store.User:
    return user_store.User(
        id=user_id,
        name="Admin",
        created_at="2026-06-03T00:00:00+00:00",
        email="admin@example.com",
        role=role,
        status=status,
        must_reset=must_reset,
        password_hash="hashed",
    )


def _patch_auth(monkeypatch: pytest.MonkeyPatch, module: Any, actor: user_store.User) -> None:
    monkeypatch.setattr(module.auth, "validate_session", lambda token, idle: actor.id)
    monkeypatch.setattr(module.auth, "has_role", lambda user, roles: user.role in roles)
    monkeypatch.setattr(module.user_store, "get_by_id", lambda user_id: actor)


def test_skill_admin_route_handlers_cover_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    actor = _user()
    _patch_auth(monkeypatch, skill_admin_api, actor)
    audits: list[tuple[Any, ...]] = []
    states: dict[str, dict[str, Any]] = {}
    provenance: dict[str, dict[str, Any]] = {}
    bindings: dict[tuple[str, str], bool] = {}
    disabled: list[tuple[str, bool]] = []
    reloaded: list[str] = []

    def state(name: str) -> dict[str, Any]:
        return states.setdefault(
            name,
            {
                "skill_name": name,
                "status": "active",
                "global_enabled": 1,
                "audit_verdict": None,
                "forced": 0,
            },
        )

    monkeypatch.setattr(
        skill_admin_api.skill_registry,
        "_parse_frontmatter",
        lambda content: {"name": "s", "description": "desc"} if content.startswith("---") else {},
    )
    monkeypatch.setattr(
        skill_admin_api, "engine_list_skills", lambda: [{"name": "s", "description": "desc"}]
    )
    monkeypatch.setattr(
        skill_admin_api, "engine_audit", lambda content: {"verdict": "pass", "rules": []}
    )
    monkeypatch.setattr(
        skill_admin_api, "engine_reload", lambda: reloaded.append("reload") or {"ok": True}
    )
    monkeypatch.setattr(
        skill_admin_api,
        "engine_set_global_disabled",
        lambda name, disabled_: disabled.append((name, disabled_)),
    )
    # skill-admin-trigger-rematerialize: stub the materialize seams so this unit test
    # never touches a real DB / filesystem.
    monkeypatch.setattr(skill_admin_api, "_rematerialize_all", lambda: [])
    monkeypatch.setattr(skill_admin_api, "_rematerialize_agent", lambda name: None)
    monkeypatch.setattr(skill_admin_api.agent_store, "get_agent_name_by_id", lambda agent_id: "ops")
    monkeypatch.setattr(
        skill_admin_api, "engine_observability", lambda name: {"skill_name": name, "hits": 3}
    )
    monkeypatch.setattr(skill_admin_api, "reflection_list_proposals", lambda: [{"id": "p1"}])
    monkeypatch.setattr(
        skill_admin_api,
        "reflection_proposal_diff",
        lambda proposal_id: {"proposal_id": proposal_id, "diff": "+body"},
    )
    monkeypatch.setattr(
        skill_admin_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "list_states",
        lambda include_archived=False: list(states.values()),
    )
    monkeypatch.setattr(skill_admin_api.skill_admin_store, "get_state", state)
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "get_source",
        lambda name: provenance.setdefault(
            name,
            {
                "skill_name": name,
                "source": "adhoc",
                "immutable_fields": None,
                "current_version": None,
            },
        ),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_source",
        lambda name, source, immutable_fields=None: provenance.__setitem__(
            name,
            {
                "skill_name": name,
                "source": source,
                "immutable_fields": immutable_fields,
                "current_version": None,
            },
        ),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "ensure_catalog_entries",
        lambda names: None,
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_audit_result",
        lambda name, verdict, rules=None: state(name).__setitem__("audit_verdict", verdict),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_status",
        lambda name, status: state(name).__setitem__("status", status),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_global_enabled",
        lambda name, enabled: state(name).__setitem__("global_enabled", int(enabled)),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "agents_enabling",
        lambda name: sorted(
            agent for (agent, skill), enabled in bindings.items() if skill == name and enabled
        ),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "drifted_agents",
        lambda name: [
            agent
            for (agent, skill), enabled in bindings.items()
            if skill == name and enabled and provenance.get(name, {}).get("source") == "managed"
        ],
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "list_agents_for_skill",
        lambda name: [
            {"agent_id": agent, "enabled": enabled}
            for (agent, skill), enabled in bindings.items()
            if skill == name
        ],
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_binding",
        lambda agent_id, name, enabled, updated_by: bindings.__setitem__((agent_id, name), enabled),
    )
    monkeypatch.setattr(
        skill_admin_api.skill_admin_store,
        "set_forced",
        lambda name, forced: state(name).__setitem__("forced", int(forced)),
    )

    auth_header = "Session token"
    valid = "---\nname: s\ndescription: desc\n---\nbody"
    assert (
        skill_admin_api.create_skill(
            skill_admin_api.SkillBody(name="s", content=valid), auth_header
        )["published"]
        is True
    )
    assert skill_admin_api.list_skills(auth_header)[0]["name"] == "s"
    provenance["s"] = {
        "skill_name": "s",
        "source": "managed",
        "immutable_fields": ["name"],
        "current_version": None,
    }
    edited = skill_admin_api.edit_skill("s", skill_admin_api.EditBody(content=valid), auth_header)
    assert edited["source"] == "managed"
    assert "immutable_warning" not in edited
    assert "drift" not in edited
    assert skill_admin_api.disable_skill("s", auth_header)["global_enabled"] == 0
    assert skill_admin_api.enable_skill("s", auth_header)["global_enabled"] == 1
    assert disabled == [("s", True), ("s", False)]
    assert skill_admin_api.reload_skills(auth_header)["ok"] is True
    assert (
        skill_admin_api.set_skill_agent_binding(
            "s", 7, skill_admin_api.BindingBody(enabled=True), auth_header
        )["enabled"]
        is True
    )
    assert skill_admin_api.list_skill_agents("s", auth_header)[0]["agent_id"] == 7
    with pytest.raises(HTTPException) as blocked:
        skill_admin_api.archive_skill("s", auth_header, "true")
    assert blocked.value.status_code == 409
    bindings[(7, "s")] = False
    assert skill_admin_api.archive_skill("s", auth_header, "true")["status"] == "archived"
    assert skill_admin_api.restore_skill("s", auth_header)["status"] == "active"
    assert skill_admin_api.force_publish("s", auth_header, "true")["forced"] == 1
    assert skill_admin_api.skill_observability("s", auth_header)["hits"] == 3
    assert skill_admin_api.list_proposals(auth_header) == [{"id": "p1"}]
    assert skill_admin_api.proposal_diff("p1", auth_header)["diff"] == "+body"
    with pytest.raises(HTTPException) as approve_blocked:
        skill_admin_api.approve_proposal("p1", auth_header, "true")
    assert approve_blocked.value.status_code == 409
    with pytest.raises(HTTPException) as reject_blocked:
        skill_admin_api.reject_proposal("p2", auth_header)
    assert reject_blocked.value.status_code == 409
    assert reloaded
    assert audits


def test_skill_admin_route_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_auth(monkeypatch, skill_admin_api, _user())
    monkeypatch.setattr(skill_admin_api.skill_registry, "_parse_frontmatter", lambda content: {})
    with pytest.raises(HTTPException) as invalid:
        skill_admin_api.create_skill(
            skill_admin_api.SkillBody(name="bad", content="missing frontmatter"),
            "Session token",
        )
    assert invalid.value.status_code == 422
    with pytest.raises(HTTPException) as missing_confirm:
        skill_admin_api.force_publish("s", "Session token", None)
    assert missing_confirm.value.status_code == 428
    monkeypatch.setattr(
        skill_admin_api, "engine_reload", lambda: {"ok": False, "error": "parse error"}
    )
    monkeypatch.setattr(skill_admin_api.audit_log, "write_audit", lambda *args, **kwargs: None)
    with pytest.raises(HTTPException) as reload_failed:
        skill_admin_api.reload_skills("Session token")
    assert reload_failed.value.status_code == 503


def test_user_admin_route_handlers_cover_management(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = _user()
    admin.password_hash = "hash:pw"
    target = _user("viewer", user_id="user-1")
    users = {admin.id: admin, target.id: target}
    audits: list[tuple[Any, ...]] = []
    keys: list[dict[str, Any]] = []
    im_rows = [{"id": 7, "platform_user_id": "U1"}]

    monkeypatch.setattr(user_admin_api.auth, "validate_session", lambda token, idle: admin.id)
    monkeypatch.setattr(user_admin_api.auth, "has_role", lambda user, roles: user.role in roles)
    monkeypatch.setattr(user_admin_api.auth, "hash_password", lambda password: f"hash:{password}")
    monkeypatch.setattr(
        user_admin_api.auth,
        "verify_password",
        lambda password, password_hash: password_hash == f"hash:{password}",
    )
    monkeypatch.setattr(user_admin_api.auth, "create_session", lambda user_id: f"session:{user_id}")
    monkeypatch.setattr(
        user_admin_api.auth, "logout", lambda token: audits.append(("logout", token))
    )
    monkeypatch.setattr(user_admin_api.user_store, "get_by_id", lambda user_id: users.get(user_id))
    monkeypatch.setattr(
        user_admin_api.user_store,
        "get_by_email",
        lambda email: next((u for u in users.values() if u.email == email), None),
    )
    monkeypatch.setattr(user_admin_api.user_store, "get_builtin_admin", lambda: admin)
    monkeypatch.setattr(user_admin_api.user_store, "list_users", lambda: list(users.values()))
    monkeypatch.setattr(
        user_admin_api.user_store,
        "create_web_user",
        lambda email, name, password_hash=None, must_reset=False, role="viewer": users.setdefault(
            "new-1",
            _user(role, user_id="new-1", must_reset=int(must_reset)),
        ),
    )
    monkeypatch.setattr(
        user_admin_api.user_store, "delete_user", lambda user_id: users.pop(user_id)
    )
    monkeypatch.setattr(
        user_admin_api.user_store,
        "set_role",
        lambda user_id, role: setattr(users[user_id], "role", role),
    )
    monkeypatch.setattr(
        user_admin_api.user_store,
        "set_password",
        lambda user_id, password_hash, must_reset=False: (
            setattr(users[user_id], "password_hash", password_hash),
            setattr(users[user_id], "must_reset", int(must_reset)),
        ),
    )
    monkeypatch.setattr(
        user_admin_api.block_service,
        "block_user",
        lambda user_id, reason, actor: setattr(users[user_id], "status", "blocked"),
    )
    monkeypatch.setattr(
        user_admin_api.block_service,
        "unblock_user",
        lambda user_id, actor: setattr(users[user_id], "status", "active"),
    )
    monkeypatch.setattr(user_admin_api.api_key_store, "list_keys", lambda user_id: keys)
    monkeypatch.setattr(
        user_admin_api.api_key_store,
        "issue_key",
        lambda user_id, scope, note, expires_at: (
            "ma-secret",
            {"id": 1, "user_id": user_id, "scope": scope},
        ),
    )
    monkeypatch.setattr(
        user_admin_api.api_key_store, "revoke_key", lambda key_id: keys.append({"revoked": key_id})
    )
    monkeypatch.setattr(user_admin_api.im, "list_all", lambda: im_rows)
    monkeypatch.setattr(
        user_admin_api.im,
        "block_im_user",
        lambda im_user_id, reason, actor: audits.append(("block_im", im_user_id)),
    )
    monkeypatch.setattr(
        user_admin_api.im,
        "restore_im_user",
        lambda im_user_id, reason, actor: audits.append(("restore_im", im_user_id)),
    )
    monkeypatch.setattr(
        user_admin_api.im,
        "rebind_im_identity",
        lambda im_user_id, user_id, actor: audits.append(("bind_im", im_user_id, user_id)),
    )
    monkeypatch.setattr(
        user_admin_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )
    monkeypatch.setattr(
        user_admin_api.audit_log,
        "search_audit",
        lambda **kwargs: [{"action": kwargs["action"] or "any"}],
    )

    auth_header = "Session token"
    assert (
        user_admin_api.login(user_admin_api.LoginBody(email=admin.email or "", password="pw"))[
            "token"
        ]
        == f"session:{admin.id}"
    )
    assert user_admin_api.logout(auth_header)["status"] == "logged_out"
    assert user_admin_api.me(auth_header)["id"] == admin.id
    assert (
        user_admin_api.change_password(
            user_admin_api.ChangePasswordBody(new_password="new"), auth_header
        )["status"]
        == "password_changed"
    )
    assert user_admin_api.list_users(auth_header)
    assert (
        user_admin_api.create_user(
            user_admin_api.CreateUserBody(email="n@example.com", name="New", password="pw"),
            auth_header,
        )["id"]
        == "new-1"
    )
    assert user_admin_api.get_user("user-1", auth_header)["role"] == "viewer"
    assert (
        user_admin_api.set_role("user-1", user_admin_api.RoleBody(role="admin"), auth_header)[
            "role"
        ]
        == "admin"
    )
    assert (
        user_admin_api.block_user("user-1", user_admin_api.ReasonBody(reason="risk"), auth_header)[
            "status"
        ]
        == "blocked"
    )
    assert user_admin_api.unblock_user("user-1", auth_header)["status"] == "active"
    assert (
        user_admin_api.reset_user_password(
            "user-1", user_admin_api.ChangePasswordBody(new_password="temp"), auth_header
        )["status"]
        == "password_reset"
    )
    assert user_admin_api.list_keys("user-1", auth_header) == []
    assert (
        user_admin_api.issue_key("user-1", user_admin_api.IssueKeyBody(scope=["ops"]), auth_header)[
            "plaintext"
        ]
        == "ma-secret"
    )
    user_admin_api.revoke_key(1, auth_header)
    assert user_admin_api.list_im_users(auth_header) == im_rows
    assert (
        user_admin_api.block_im_user(7, user_admin_api.ReasonBody(reason="spam"), auth_header)[
            "allowed"
        ]
        is False
    )
    assert (
        user_admin_api.restore_im_user(7, user_admin_api.ReasonBody(), auth_header)["allowed"]
        is True
    )
    assert (
        user_admin_api.bind_im_user(7, user_admin_api.BindImBody(user_id="user-1"), auth_header)[
            "status"
        ]
        == "bound"
    )
    assert (
        user_admin_api.search_audit(action="delete_user", authorization=auth_header)[0]["action"]
        == "delete_user"
    )
    user_admin_api.delete_user("user-1", auth_header)
    assert "user-1" not in users


def test_user_admin_route_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    admin = _user()
    monkeypatch.setattr(user_admin_api.auth, "validate_session", lambda token, idle: admin.id)
    monkeypatch.setattr(user_admin_api.auth, "has_role", lambda user, roles: user.role in roles)
    monkeypatch.setattr(user_admin_api.user_store, "get_by_id", lambda user_id: admin)
    monkeypatch.setattr(user_admin_api.user_store, "get_by_email", lambda email: None)
    with pytest.raises(HTTPException) as login_failed:
        user_admin_api.login(user_admin_api.LoginBody(email="missing@example.com", password="pw"))
    assert login_failed.value.status_code == 401
    monkeypatch.setattr(
        user_admin_api.user_store,
        "get_by_id",
        lambda user_id: None if user_id == "missing" else admin,
    )
    with pytest.raises(HTTPException) as missing:
        user_admin_api.get_user("missing", "Session token")
    assert missing.value.status_code == 404


def test_chat_admin_route_handlers_cover_governance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actor = _user()
    _patch_auth(monkeypatch, chat_admin_api, actor)
    metas: dict[str, dict[str, Any]] = {}
    audits: list[tuple[Any, ...]] = []
    cleared: list[str] = []
    injected: list[tuple[str, str, str]] = []
    delivered: list[tuple[str, str]] = []
    resets: list[tuple[str, int]] = []

    def upsert_meta(session_id: str, **kwargs: Any) -> None:
        metas.setdefault(
            session_id,
            {"session_id": session_id, "origin": kwargs.get("origin", "web"), "status": "active"},
        )
        metas[session_id].update(kwargs)
        if "agent_id" in kwargs and "agent_name" not in metas[session_id]:
            metas[session_id]["agent_name"] = "ops"

    monkeypatch.setattr(
        chat_admin_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )
    monkeypatch.setattr(
        chat_admin_api, "get_agent_by_name", lambda name: SimpleNamespace(id=7, name=name)
    )
    monkeypatch.setattr(chat_admin_api.session_admin_store, "upsert_meta", upsert_meta)
    monkeypatch.setattr(
        chat_admin_api.session_admin_store,
        "get_meta",
        lambda session_id: metas.setdefault(
            session_id,
            {"session_id": session_id, "origin": "web", "agent_name": "ops", "status": "active"},
        ),
    )
    monkeypatch.setattr(
        chat_admin_api.session_admin_store,
        "delete_meta",
        lambda session_id: metas.pop(session_id, None),
    )
    monkeypatch.setattr(
        chat_admin_api.session_admin_store,
        "set_status",
        lambda session_id, status: metas.setdefault(
            session_id, {"session_id": session_id, "origin": "web"}
        ).__setitem__("status", status),
    )
    monkeypatch.setattr(
        chat_admin_api.session_admin_store, "list_meta", lambda **kwargs: list(metas.values())
    )
    monkeypatch.setattr(
        chat_admin_api.session_admin_store,
        "set_takeover",
        lambda session_id, user_id: metas.setdefault(
            session_id, {"session_id": session_id}
        ).__setitem__("takeover_by", user_id),
    )
    monkeypatch.setattr(
        chat_admin_api.session_admin_store,
        "clear_takeover",
        lambda session_id: metas.setdefault(session_id, {"session_id": session_id}).pop(
            "takeover_by", None
        ),
    )
    monkeypatch.setattr(
        chat_admin_api,
        "session_stats",
        lambda session_id: {"total_tokens": 10, "rounds": 2, "pending_approvals": 0},
    )
    monkeypatch.setattr(
        chat_admin_api, "load_transcript", lambda session_id: [{"role": "user", "content": "hi"}]
    )
    monkeypatch.setattr(
        chat_admin_api, "clear_session", lambda session_id: cleared.append(session_id)
    )
    monkeypatch.setattr(
        chat_admin_api,
        "inject",
        lambda session_id, role, content: injected.append((session_id, role, content)),
    )
    monkeypatch.setattr(
        chat_admin_api,
        "im_deliver",
        lambda session_id, content: delivered.append((session_id, content)),
    )
    monkeypatch.setattr(
        chat_admin_api,
        "reset_session",
        lambda session_id, keep_turns: resets.append((session_id, keep_turns)),
    )

    auth_header = "Session token"
    metas["im-1"] = {
        "session_id": "im-1",
        "origin": "im",
        "status": "active",
        "agent_id": 7,
        "agent_name": "ops",
    }
    assert (
        chat_admin_api.list_sessions(agent_name="ops", authorization=auth_header)[0]["total_tokens"]
        == 10
    )
    assert chat_admin_api.session_detail("im-1", auth_header)["transcript"][0]["role"] == "user"
    assert chat_admin_api.takeover("im-1", auth_header)["taken_over"] is True
    assert (
        chat_admin_api.inject_message(
            "im-1", chat_admin_api.InjectBody(content="human"), auth_header
        )["injected"]
        is True
    )
    assert delivered == [("im-1", "human")]
    assert chat_admin_api.release("im-1", auth_header)["taken_over"] is False
    assert (
        chat_admin_api.bulk_dispose(
            chat_admin_api.BulkBody(session_ids=["a", "b"], action="end"), auth_header, "true"
        )["count"]
        == 2
    )
    assert chat_admin_api.force_end("im-1", auth_header, "true")["status"] == "ended"
    assert chat_admin_api.clear("im-1", auth_header, "true")["cleared"] is True
    assert (
        chat_admin_api.reset("im-1", chat_admin_api.ResetBody(keep_turns=1), auth_header, "true")[
            "keep_turns"
        ]
        == 1
    )
    assert cleared == ["im-1"]
    assert injected == [("im-1", "human_agent", "human")]
    assert resets == [("im-1", 1)]
    assert audits


def test_chat_admin_route_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_auth(monkeypatch, chat_admin_api, _user())
    monkeypatch.setattr(chat_admin_api, "get_agent_by_name", lambda name: None)
    with pytest.raises(HTTPException) as missing_agent:
        chat_admin_api.list_sessions(agent_name="missing", authorization="Session token")
    assert missing_agent.value.status_code == 404
    with pytest.raises(HTTPException) as missing_confirm:
        chat_admin_api.force_end("web-1", "Session token")
    assert missing_confirm.value.status_code == 428
    with pytest.raises(HTTPException) as invalid_bulk:
        chat_admin_api.bulk_dispose(
            chat_admin_api.BulkBody(session_ids=["s"], action="delete"), "Session token", "true"
        )
    assert invalid_bulk.value.status_code == 422


def test_provider_admin_handlers_cover_crud_health_and_observation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_auth(monkeypatch, provider_admin_api, _user())
    providers: dict[str, dict[str, Any]] = {}
    audits: list[tuple[Any, ...]] = []

    def add_provider(provider_id: str, **kwargs: Any) -> None:
        providers[provider_id] = {
            "id": provider_id,
            "base_url": kwargs["base_url"],
            "model": kwargs["model"],
            "api_key": kwargs.get("api_key"),
            "max_tokens": kwargs.get("max_tokens"),
            "temperature": kwargs.get("temperature"),
            "extra_params": kwargs.get("extra_params"),
            "input_price_per_1k": None,
            "output_price_per_1k": None,
        }

    monkeypatch.setattr(
        provider_admin_api.provider_admin_store, "list_providers", lambda: list(providers.values())
    )
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store,
        "get_provider",
        lambda provider_id: providers.get(provider_id),
    )
    monkeypatch.setattr(provider_admin_api.provider_admin_store, "add_provider", add_provider)
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store,
        "edit_provider",
        lambda provider_id, **changes: providers[provider_id].update(changes),
    )
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store,
        "delete_provider",
        lambda provider_id: providers.pop(provider_id, None),
    )
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store,
        "set_pricing",
        lambda provider_id, input_price, output_price: providers[provider_id].update(
            {"input_price_per_1k": input_price, "output_price_per_1k": output_price}
        ),
    )
    monkeypatch.setattr(
        provider_admin_api,
        "router_health_probe",
        lambda: {"p1": {"available": False, "recovers_at": "later"}},
    )
    monkeypatch.setattr(
        provider_admin_api,
        "router_connectivity_test",
        lambda provider: {"reachable": True, "latency_ms": 12, "model": provider["model"]},
    )
    monkeypatch.setattr(
        provider_admin_api,
        "provider_observability",
        lambda provider_id: {"provider_id": provider_id, "calls": 5},
    )
    monkeypatch.setattr(
        provider_admin_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )

    auth_header = "Session token"
    created = provider_admin_api.add_provider(
        provider_admin_api.ProviderBody(
            id="p1", base_url="https://models.local", model="gpt", api_key="secret"
        ),
        auth_header,
    )
    assert created["api_key"] == "****"
    assert created["api_key_set"] is True
    assert provider_admin_api.list_providers(auth_header)[0]["id"] == "p1"
    assert (
        provider_admin_api.edit_provider(
            "p1", provider_admin_api.ProviderEditBody(model="gpt-next"), auth_header
        )["model"]
        == "gpt-next"
    )
    assert provider_admin_api.health(auth_header)["providers"][0]["available"] is False
    assert provider_admin_api.connectivity_test("p1", auth_header)["reachable"] is True
    pricing = provider_admin_api.set_pricing(
        "p1", provider_admin_api.PricingBody(input_price_per_1k=0.1), auth_header
    )
    assert pricing["output_price_per_1k"] == "未配置"
    assert provider_admin_api.observability("p1", auth_header)["calls"] == 5
    assert provider_admin_api.delete_provider("p1", auth_header)["deleted"] is True
    assert audits


def test_provider_admin_route_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_auth(monkeypatch, provider_admin_api, _user())
    providers = {"p1": {"id": "p1", "api_key": None}}
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store,
        "get_provider",
        lambda provider_id: providers.get(provider_id),
    )
    monkeypatch.setattr(
        provider_admin_api.provider_admin_store, "add_provider", lambda *args, **kwargs: None
    )
    with pytest.raises(HTTPException) as duplicate:
        provider_admin_api.add_provider(
            provider_admin_api.ProviderBody(id="p1", base_url="u", model="m"),
            "Session token",
        )
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as missing:
        provider_admin_api.edit_provider(
            "missing", provider_admin_api.ProviderEditBody(model="m"), "Session token"
        )
    assert missing.value.status_code == 404


def test_kb_admin_route_handlers_cover_management_and_documents(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_auth(monkeypatch, kb_admin_api, _user())
    kbs: dict[str, dict[str, Any]] = {
        "kb1": {"kb_id": "kb1", "description": "Operations", "archived": False}
    }
    bindings: dict[tuple[str, str], set[int]] = {("default", "kb1"): {7}}
    audits: list[tuple[Any, ...]] = []
    deleted_docs: list[str] = []

    monkeypatch.setattr(kb_admin_api, "kb_engine_list", lambda tenant_id: list(kbs.values()))
    monkeypatch.setattr(
        kb_admin_api,
        "kb_engine_create",
        lambda tenant_id, kb_id, description: kbs.__setitem__(
            kb_id, {"kb_id": kb_id, "description": description, "archived": False}
        ),
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_engine_edit",
        lambda tenant_id, kb_id, description: kbs[kb_id].__setitem__("description", description),
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_engine_archive",
        lambda tenant_id, kb_id: kbs[kb_id].__setitem__("archived", True),
    )
    monkeypatch.setattr(kb_admin_api, "_require_active_kb", lambda tenant_id, kb_id: None)
    monkeypatch.setattr(
        kb_admin_api,
        "kb_ingest_text",
        lambda tenant_id, kb_id, source, content, document_format: {
            "document_id": "doc-1",
            "chunks": 2,
        },
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_sync_directory",
        lambda tenant_id, kb_id, path: {"scanned": 3, "ingested": 2, "skipped": 1, "failed": 0},
    )
    monkeypatch.setattr(
        kb_admin_api,
        "_enqueue_import_job",
        lambda kb_id, body: {"id": "job-import-1", "kb_id": kb_id, "tenant_id": body.tenant_id},
    )
    monkeypatch.setattr(
        kb_admin_api,
        "_enqueue_sync_directory_job",
        lambda kb_id, body: {"id": "job-sync-1", "kb_id": kb_id, "tenant_id": body.tenant_id},
    )
    monkeypatch.setattr(
        kb_admin_api,
        "_wait_for_kb_ingest_job",
        lambda job_id: (
            {"job_id": job_id, "document_id": "doc-1", "chunks": 2}
            if job_id == "job-import-1"
            else {"job_id": job_id, "scanned": 3, "ingested": 2, "skipped": 1, "failed": 0}
        ),
    )
    monkeypatch.setattr(
        kb_admin_api, "kb_list_documents", lambda tenant_id, kb_id: [{"document_id": "doc-1"}]
    )
    monkeypatch.setattr(
        kb_admin_api, "kb_chunk_preview", lambda tenant_id, kb_id, document_id: [{"chunk_id": "c1"}]
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_delete_document",
        lambda tenant_id, kb_id, document_id: deleted_docs.append(document_id),
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_search",
        lambda query, tenant_id, kb_ids, mode, limit: [{"document_id": "doc-1", "score": 0.9}],
    )
    monkeypatch.setattr(
        kb_admin_api,
        "kb_evaluation",
        lambda tenant_id, kb_id: {"kb_id": kb_id, "metrics": {"recall": 1.0}},
    )
    monkeypatch.setattr(
        kb_admin_api, "kb_observation", lambda tenant_id, kb_id: {"kb_id": kb_id, "recall_hits": 7}
    )
    monkeypatch.setattr(
        kb_admin_api.agent_kbs_store,
        "list_agents_for_kb",
        lambda tenant_id, kb_id: sorted(bindings.get((tenant_id, kb_id), set())),
    )
    monkeypatch.setattr(
        kb_admin_api.agent_kbs_store,
        "list_kbs_for_agent",
        lambda tenant_id, agent_id: [
            kb_id
            for (tenant, kb_id), agents in bindings.items()
            if tenant == tenant_id and agent_id in agents
        ],
    )
    monkeypatch.setattr(
        kb_admin_api.agent_kbs_store,
        "is_kb_bound",
        lambda tenant_id, kb_id: bool(bindings.get((tenant_id, kb_id))),
    )
    monkeypatch.setattr(
        kb_admin_api.agent_kbs_store,
        "bind",
        lambda tenant_id, kb_id, agent_id, created_by: bindings.setdefault(
            (tenant_id, kb_id), set()
        ).add(agent_id),
    )
    monkeypatch.setattr(
        kb_admin_api.agent_kbs_store,
        "unbind",
        lambda tenant_id, kb_id, agent_id: bindings.setdefault((tenant_id, kb_id), set()).discard(
            agent_id
        ),
    )
    monkeypatch.setattr(
        kb_admin_api.audit_log, "write_audit", lambda *args, **kwargs: audits.append(args)
    )

    auth_header = "Session token"
    assert kb_admin_api.list_kbs(authorization=auth_header)[0]["bound_agents"] == [7]
    assert (
        kb_admin_api.create_kb(
            kb_admin_api.KbBody(kb_id="kb2", description="Policies"), auth_header
        )["kb_id"]
        == "kb2"
    )
    assert (
        kb_admin_api.edit_kb(
            "kb2", kb_admin_api.KbEditBody(description="Policies v2"), authorization=auth_header
        )["description"]
        == "Policies v2"
    )
    assert (
        kb_admin_api.import_document(
            "kb2", kb_admin_api.ImportBody(source="paste", content="body"), auth_header
        )["chunks"]
        == 2
    )
    assert (
        kb_admin_api.sync_directory(
            "kb2", kb_admin_api.SyncBody(path="/data/docs"), auth_header, "true"
        )["ingested"]
        == 2
    )
    assert (
        kb_admin_api.list_documents("kb2", authorization=auth_header)[0]["document_id"] == "doc-1"
    )
    assert (
        kb_admin_api.preview_chunks("kb2", "doc-1", authorization=auth_header)[0]["chunk_id"]
        == "c1"
    )
    assert (
        kb_admin_api.delete_document("kb2", "doc-1", authorization=auth_header, x_confirm="true")[
            "deleted"
        ]
        is True
    )
    assert deleted_docs == ["doc-1"]
    assert (
        kb_admin_api.retrieval_playground(
            kb_admin_api.SearchBody(query="q", kb_ids=["kb2"]), auth_header
        )["results"][0]["score"]
        == 0.9
    )
    assert (
        kb_admin_api.run_evaluation(kb_admin_api.EvalBody(kb_id="kb2"), auth_header)["metrics"][
            "recall"
        ]
        == 1.0
    )
    assert (
        kb_admin_api.bind_agent("kb2", kb_admin_api.BindBody(agent_id=8), auth_header)["bound"]
        is True
    )
    assert kb_admin_api.agents_for_kb("kb2", authorization=auth_header)["agents"] == [8]
    assert kb_admin_api.kbs_for_agent(8, authorization=auth_header)["kb_ids"] == ["kb2"]
    assert kb_admin_api.unbind_agent("kb2", 8, authorization=auth_header)["bound"] is False
    assert kb_admin_api.observation("kb2", authorization=auth_header)["recall_hits"] == 7
    with pytest.raises(HTTPException) as still_bound:
        kb_admin_api.archive_kb("kb1", authorization=auth_header, x_confirm="true")
    assert still_bound.value.status_code == 409
    bindings[("default", "kb1")] = set()
    assert (
        kb_admin_api.archive_kb("kb1", authorization=auth_header, x_confirm="true")["archived"]
        is True
    )
    assert audits


def test_kb_admin_route_error_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_auth(monkeypatch, kb_admin_api, _user())
    monkeypatch.setattr(kb_admin_api, "kb_engine_list", lambda tenant_id: [{"kb_id": "kb1"}])
    with pytest.raises(HTTPException) as duplicate:
        kb_admin_api.create_kb(kb_admin_api.KbBody(kb_id="kb1"), "Session token")
    assert duplicate.value.status_code == 409
    with pytest.raises(HTTPException) as invalid_mode:
        kb_admin_api.retrieval_playground(
            kb_admin_api.SearchBody(query="q", kb_ids=["kb1"], mode="bad"),
            "Session token",
        )
    assert invalid_mode.value.status_code == 422
    monkeypatch.setattr(kb_admin_api.agent_kbs_store, "is_kb_bound", lambda tenant_id, kb_id: False)
    with pytest.raises(HTTPException) as confirm:
        kb_admin_api.sync_directory("kb1", kb_admin_api.SyncBody(path="/tmp"), "Session token")
    assert confirm.value.status_code == 428


def test_server_helpers_cover_admin_url_jobs_and_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(server.sys, "argv", ["uvicorn", "--host=0.0.0.0", "--port", "9000"])
    assert server._admin_login_url("/admin") == "http://127.0.0.1:9000/admin/ui"
    assert not hasattr(server, "_run_playground_retention")


async def test_server_auth_health_and_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.identity import Principal

    monkeypatch.setattr(
        server,
        "_platform_bearer",
        lambda api_key: (
            Principal(user_id="u1", tenant_id="default") if api_key == "ma-valid" else None
        ),
    )
    resolved = await server._authenticate("Bearer ma-valid")
    assert resolved.user_id == "u1"
    with pytest.raises(HTTPException) as invalid_auth:
        await server._authenticate("Basic nope")
    assert invalid_auth.value.status_code == 401

    # Slack is per-agent (agent.yaml im.slack); Telegram is owner-level.
    monkeypatch.setattr(server, "_slack_adapter_configured", lambda: True)
    monkeypatch.setattr(server, "_telegram_adapter_configured", lambda: False)
    health = await server.health(
        SimpleNamespace(
            app=SimpleNamespace(
                state=SimpleNamespace(
                    sandbox_mode=server.Mode.OFF,
                    sandbox_backend="docker",
                    sandbox_backend_available=False,
                )
            )
        )
    )
    assert health["adapters"]["slack"] is True
    assert health["sandbox"]["backend"] == "docker"
    assert health["sandbox"]["backend_available"] is False
    assert health["sandbox"]["note"] == "off (docker unavailable)"

    async def resolve(**kwargs: Any) -> bool:
        return kwargs["approval_id"] == "a1"

    monkeypatch.setattr(server, "resolve_approval_request", resolve)
    assert (
        await server.resolve_approval(
            "a1", server.ApprovalRequest(decision="approved", approver_user_id="ops")
        )
    )["status"] == "ok"
    with pytest.raises(HTTPException) as bad_decision:
        await server.resolve_approval("a1", server.ApprovalRequest(decision="maybe"))
    assert bad_decision.value.status_code == 400
    with pytest.raises(HTTPException) as missing_approval:
        await server.resolve_approval("missing", server.ApprovalRequest(decision="approved"))
    assert missing_approval.value.status_code == 404
