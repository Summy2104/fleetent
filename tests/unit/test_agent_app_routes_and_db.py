from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException
from starlette.websockets import WebSocketDisconnect

from fleetent.identity import Principal, encode_ingress_principal
from fleetent.integrations.sandbox import Mode
from fleetent.runtime import agent_app


def _route(app: Any, path: str) -> Any:
    for route in app.routes:
        if getattr(route, "path", None) == path:
            return route
    raise AssertionError(f"route {path} not found")


def _agent_file(**overrides: Any) -> Any:
    agent = SimpleNamespace(
        name="ops",
        tenant_id="tenant-1",
        system_prompt="prompt",
        allowed_tools=["shell"],
        plugins=["github"],
        features={"code_execution": True},
        allowed_skills=["triage"],
        skill_authoring_enabled=False,
        skill_hot_reload=True,
        skill_user_access={},
        mcp_servers=[],
        mcp=SimpleNamespace(enabled=True, tool_naming="claude"),
        scheduling=SimpleNamespace(enabled=False),
    )
    for key, value in overrides.items():
        setattr(agent, key, value)
    return agent


async def _collect_stream(response: Any) -> list[str]:
    return [chunk async for chunk in response.body_iterator]


def test_init_agent_db_schema_wires_router_and_sinks(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    tenant_scope = SimpleNamespace(
        kb_vector_backend="kb-vector",
        open_kb_db=lambda migrations: ("kb-db", migrations),
    )
    agent_scope = SimpleNamespace(
        vector_backend="agent-vector",
        agent_memory_vector_backend="agent-memory-vector",
        open_state_db=lambda migrations: ("state-db", migrations),
        open_agent_memory_db=lambda migrations: ("agent-memory-db", migrations),
    )
    captures: list[tuple[str, Any]] = []

    class _Router:
        def tenant_scope(self, tenant_id: str) -> Any:
            captures.append(("tenant_scope", tenant_id))
            return tenant_scope

        def agent_scope(self, tenant_id: str, agent_id: str) -> Any:
            captures.append(("agent_scope", (tenant_id, agent_id)))
            return agent_scope

    monkeypatch.setattr(
        "fleetent.tenant_router.SQLiteTenantBackend", lambda data_dir: ("backend", data_dir)
    )
    monkeypatch.setattr("fleetent.tenant_router.TenantRouter", lambda backend: _Router())
    monkeypatch.setattr(
        "fleetent.knowledge_base.runtime.set_database", lambda db: captures.append(("kb_db", db))
    )
    monkeypatch.setattr(
        "fleetent.knowledge_base.runtime.set_vector_backend",
        lambda backend: captures.append(("kb_vector", backend)),
    )
    monkeypatch.setattr(
        "fleetent.memory.agent_memory.set_agent_memory_db",
        lambda db, backend: captures.append(("agent_memory", (db, backend))),
    )
    for target, key in (
        ("fleetent.session.index.set_state_db", "session_index"),
        ("fleetent.observability.traces.set_state_db", "traces"),
        ("fleetent.reflection.set_state_db", "reflection"),
        ("fleetent.memory.store.set_state_db", "memory_db"),
        ("fleetent.governance.approval_request_store.set_state_db", "approval_request"),
        ("fleetent.governance.approval_store.set_state_db", "approval_store"),
        ("fleetent.governance.tool_auto_approvals_store.set_state_db", "allowlist"),
        ("fleetent.runtime.context.set_state_db", "context"),
        ("fleetent.runtime.sub_agent_lifecycle.set_state_db", "sub_agents"),
        ("fleetent.schedule_store.set_state_db", "schedule"),
        ("fleetent.artifact_exchange.set_state_db", "artifact_db"),
    ):
        monkeypatch.setattr(target, lambda db, _key=key: captures.append((_key, db)))
    monkeypatch.setattr(
        "fleetent.memory.store.set_vector_backend",
        lambda backend: captures.append(("agent_vector", backend)),
    )
    monkeypatch.setattr(
        "fleetent.artifact_exchange.set_views_root",
        lambda root: captures.append(("views_root", root)),
    )

    agent_app._init_agent_db_schema(tmp_path / "data", agent_id="ops", tenant_id="tenant-1")

    assert ("tenant_scope", "tenant-1") in captures
    assert ("agent_scope", ("tenant-1", "ops")) in captures
    assert ("kb_vector", "kb-vector") in captures
    assert ("agent_vector", "agent-vector") in captures
    assert any(key == "artifact_db" for key, _ in captures)
    assert ("views_root", tmp_path / "exchange" / ".views") in captures


async def test_start_infra_registers_mcp_and_resume_markers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    mcp_server = SimpleNamespace(
        id="files",
        transport="stdio",
        url=None,
        auth_type="none",
        api_key_env=None,
        command="cmd",
        args=("a",),
        env={"X": "1"},
        headers={"H": "1"},
        connect_timeout=3.0,
        call_timeout=5.0,
        approval_rules=("rule",),
    )
    agent = _agent_file(mcp_servers=[mcp_server])
    register_all = AsyncMock()
    monkeypatch.setattr(agent_app, "_init_agent_db_schema", lambda *args, **kwargs: None)
    # _start_infra reconciles expired approvals (#8) after the (here NOOP'd) state_db wiring.
    monkeypatch.setattr("fleetent.runtime.approval_resume.reconcile_expired_approvals", AsyncMock())
    monkeypatch.setattr(
        "fleetent.integrations.sandbox.factory.create_backend",
        lambda current_agent: "backend",
    )
    monkeypatch.setattr(
        "fleetent.tools.builtin_tools.init_sandbox_manager",
        lambda current_agent, **kwargs: None,
    )
    monkeypatch.setattr(
        "fleetent.integrations.sandbox.enablement.get_effective_mode",
        AsyncMock(return_value=Mode.OFF),
    )
    monkeypatch.setattr(
        "fleetent.runtime.approval_resume.reconcile_expired_approvals",
        AsyncMock(return_value=0),
    )
    monkeypatch.setattr("fleetent.integrations.mcp.register_all", register_all)
    monkeypatch.setattr("fleetent.session.manager.start_session_maintenance", lambda: None)
    monkeypatch.setattr(
        "fleetent.session.manager.scan_and_mark_recent_resume",
        lambda: ["s1"],
    )

    await agent_app._start_infra(agent, tmp_path / "data")

    register_all.assert_awaited_once()
    args, kwargs = register_all.await_args
    assert len(args[0]) == 1
    assert args[0][0].id == "files"
    assert kwargs["agent_home"] == tmp_path


async def test_build_app_chat_approvals_and_stream_error(monkeypatch: pytest.MonkeyPatch) -> None:
    events = [{"type": "text_delta", "content": "hi"}, {"type": "done", "content": "done"}]

    async def run_stream(message: str, **kwargs: Any):
        for event in events:
            yield event

    monkeypatch.setattr(
        agent_app.agent_config,
        "current",
        lambda: SimpleNamespace(get=lambda name: _agent_file()),
    )
    monkeypatch.setattr("fleetent.runtime.loop.run_stream", run_stream)
    monkeypatch.setattr(
        "fleetent.tools.plugin_loader.expand_plugin_patterns", lambda plugins: ["plugin-tool"]
    )
    monkeypatch.setattr(
        "fleetent.runtime.snapshot._governance_from_file", lambda agent: {"mode": "strict"}
    )
    monkeypatch.setattr(
        "fleetent.model.ModelPolicySnapshot.from_agent",
        lambda agent: {"policy": "fast"},
    )
    monkeypatch.setattr(
        "fleetent.governance.permission_gate.list_approvals",
        lambda status=None: [{"status": status}],
    )

    async def resolve(**kwargs: Any) -> bool:
        return kwargs["approval_id"] == "a1"

    monkeypatch.setattr("fleetent.governance.approval_router.resolve_approval_request", resolve)

    app = agent_app.build_app("ops")
    health = await _route(app, "/health").endpoint()
    assert health == {"status": "ok", "agent": "ops"}
    assert await _route(app, "/approvals").endpoint("pending") == [{"status": "pending"}]
    assert (
        await _route(app, "/approvals/{approval_id}/resolve").endpoint(
            "a1", agent_app.ApprovalRequest(decision="approved", approver_user_id="u1")
        )
    )["status"] == "ok"
    with pytest.raises(HTTPException, match="not found"):
        await _route(app, "/approvals/{approval_id}/resolve").endpoint(
            "missing", agent_app.ApprovalRequest(decision="approved", approver_user_id="u1")
        )

    response = await _route(app, "/chat").endpoint(
        agent_app.ChatRequest(message="hello"),
        Principal(user_id="u1", tenant_id="tenant-1"),
    )
    payload = "".join(await _collect_stream(response))
    assert '"type": "text_delta"' in payload
    assert '"type": "done"' in payload

    async def boom_stream(message: str, **kwargs: Any):
        raise RuntimeError("boom")
        yield  # pragma: no cover

    monkeypatch.setattr("fleetent.runtime.loop.run_stream", boom_stream)
    error_app = agent_app.build_app("ops")
    response = await _route(error_app, "/chat").endpoint(
        agent_app.ChatRequest(message="hello"),
        Principal(user_id="u1", tenant_id="tenant-1"),
    )
    assert '"type": "error"' in "".join(await _collect_stream(response))

    with pytest.raises(HTTPException, match="cross-tenant"):
        await _route(app, "/chat").endpoint(
            agent_app.ChatRequest(message="hello"),
            Principal(user_id="u1", tenant_id="other"),
        )


async def test_build_app_im_route_carries_principal_and_returns_sync_replies(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def fake_route(msg: Any, principal: Principal | None = None) -> None:
        captured["msg"] = msg
        captured["principal"] = principal
        await msg.reply_func("node-managed reply")

    monkeypatch.setattr(
        agent_app.agent_config,
        "current",
        lambda: SimpleNamespace(get=lambda name: _agent_file()),
    )
    monkeypatch.setattr("fleetent.im_gateway.normalizer.route", fake_route)

    app = agent_app.build_app("ops")
    response = await _route(app, "/im/route").endpoint(
        agent_app.ImRouteRequest(
            platform="slack",
            session_id="session-1",
            user_id="u-real",
            text="hello",
            channel_id="C1",
            agent_name="ops",
            session_context=agent_app.ImSessionContextRequest(
                platform="slack",
                sender_id="U123",
                sender_name="Alice",
                chat_type="dm",
                channel_name="C1",
            ),
        ),
        Principal(user_id="u-real", tenant_id="tenant-1"),
    )

    assert response.model_dump() == {"replies": [{"text": "node-managed reply", "blocks": None}]}
    assert captured["principal"] == Principal(user_id="u-real", tenant_id="tenant-1")
    assert captured["msg"].user_id == "u-real"
    assert captured["msg"].agent_name == "ops"

    with pytest.raises(HTTPException, match="cross-tenant"):
        await _route(app, "/im/route").endpoint(
            agent_app.ImRouteRequest(
                platform="slack",
                session_id="session-1",
                user_id="u-real",
                text="hello",
            ),
            Principal(user_id="u-real", tenant_id="other"),
        )


class _FakeWebSocket:
    def __init__(self, headers: dict[str, str], messages: list[str]) -> None:
        self.headers = headers
        self._messages = list(messages)
        self.closed: list[int] = []
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000) -> None:
        self.closed.append(code)

    async def receive_text(self) -> str:
        if self._messages:
            return self._messages.pop(0)
        raise WebSocketDisconnect()

    async def send_text(self, text: str) -> None:
        self.sent.append(text)


async def test_build_app_ws_gateway_branches(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        agent_app.agent_config,
        "current",
        lambda: SimpleNamespace(get=lambda name: _agent_file()),
    )
    app = agent_app.build_app("ops")
    endpoint = _route(app, "/ws").endpoint

    rejected = _FakeWebSocket({"authorization": "Bearer bad"}, [])
    monkeypatch.setattr(agent_app, "_validate_tui_token", lambda auth: None)
    await endpoint(rejected)
    assert rejected.closed == [1008]

    cross_tenant = _FakeWebSocket({"authorization": "Bearer ok"}, [])
    monkeypatch.setattr(
        agent_app,
        "_validate_tui_token",
        lambda auth: Principal(user_id="u1", tenant_id="other"),
    )
    await endpoint(cross_tenant)
    assert cross_tenant.closed == [1008]

    ws = _FakeWebSocket(
        {"authorization": "Bearer ok"},
        ["not-json", json.dumps({"id": 1, "method": "send", "params": {}})],
    )
    monkeypatch.setattr(
        agent_app,
        "_validate_tui_token",
        lambda auth: Principal(user_id="u1", tenant_id="tenant-1"),
    )
    monkeypatch.setattr(
        "fleetent.tui.dispatch.dispatch",
        AsyncMock(return_value={"jsonrpc": "2.0", "id": 1, "result": {"ok": True}}),
    )
    await endpoint(ws)
    assert ws.accepted is True
    assert any("gateway.ready" in frame for frame in ws.sent)
    assert any('"error"' in frame for frame in ws.sent)
    assert any('"result"' in frame for frame in ws.sent)

    carried_ws = _FakeWebSocket(
        {
            "authorization": "Bearer ok",
            "x-fleetent-principal": encode_ingress_principal(
                Principal(user_id="operator-1", tenant_id="tenant-1")
            ),
        },
        [json.dumps({"id": 2, "method": "send", "params": {"message": "hi"}})],
    )
    dispatch_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(
        agent_app,
        "_validate_tui_token",
        lambda auth: Principal(user_id="local", tenant_id="default"),
    )
    monkeypatch.setattr("fleetent.tui.dispatch.dispatch", dispatch_mock)
    await endpoint(carried_ws)
    assert dispatch_mock.await_args.args[0].principal == Principal(
        user_id="operator-1", tenant_id="tenant-1"
    )
