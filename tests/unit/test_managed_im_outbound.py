from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod


def _enable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FLEETENT_NODE_ID", "node-a")
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", "https://platform.internal")
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-" + "1" * 64)


def _agent(enabled: bool = True, name: str = "support") -> MagicMock:
    agent = MagicMock()
    agent.name = name
    agent.scheduling.enabled = enabled
    return agent


def test_resolve_for_runtime_prefers_live_connector() -> None:
    from fleetent.outbound_connectors import resolve_for_runtime

    live = object()
    resolved = resolve_for_runtime("support", {"slack": live})

    assert resolved == {"slack": live}


async def test_start_scheduler_resolver_returns_managed_queue_connectors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.runtime import agent_app

    _enable_node_managed_env(monkeypatch)

    captured: dict[str, object] = {}

    def _fake_ctor(settings=None, connectors_resolver=None):  # type: ignore[no-untyped-def]
        captured["resolver"] = connectors_resolver
        inst = MagicMock()
        inst.start = AsyncMock()
        return inst

    monkeypatch.setattr("fleetent.cron_scheduler.CronScheduler", _fake_ctor)

    await agent_app._start_scheduler(_agent(enabled=True, name="support"))

    resolved = captured["resolver"]()
    assert set(resolved) == {"slack", "telegram"}
    assert all(type(conn).__name__ == "ManagedOutboundConnector" for conn in resolved.values())


@pytest.fixture(autouse=True)
def _mock_approval_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.governance import approval_store, tool_auto_approvals_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(tool_auto_approvals_store, "is_allowed", MagicMock(return_value=False))


async def test_permission_gate_queues_managed_approval_dm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.agent_config import ApprovalRouting
    from fleetent.governance.permission_gate import PermissionGate
    from fleetent.outbound_connectors import resolve_for_runtime

    _enable_node_managed_env(monkeypatch)

    queued: list[dict[str, object]] = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: queued.append(kwargs) or {"id": "q1"},
    )

    gate = PermissionGate(high_timeout=1.0)
    routing = ApprovalRouting(by_risk={"high": {"approvers": ["slack:U_LEAD"], "policy": "any"}})

    result = await gate.request_approval(
        approval_id="approval-1",
        risk_level="high",
        tool_name="send_im_message",
        tool_args={"target": "U_TARGET", "text": "hello"},
        requester_user_id="u1",
        reply_func=AsyncMock(),
        session_id="session-1",
        approval_routing=routing,
        outbound_connectors=resolve_for_runtime("support", {}),
    )

    assert result == "pending"
    assert len(queued) == 1
    assert queued[0]["platform"] == "slack"


async def test_send_im_message_queues_when_node_managed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.outbound_connectors import resolve_for_runtime
    from fleetent.tools.builtin_tools import send_im_message
    from fleetent.tools.registry import ToolContext

    _enable_node_managed_env(monkeypatch)

    queued: list[dict[str, object]] = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: queued.append(kwargs) or {"id": "q1"},
    )

    ctx = ToolContext(
        agent_name="support",
        run_id="run-1",
        session_context=SessionContext(platform="slack", sender_id="U_SENDER"),
        outbound_connectors=resolve_for_runtime("support", {}),
    )

    result = await send_im_message(target="U_OTHER", text="hello", tool_context=ctx)

    assert "U_OTHER" in result
    assert len(queued) == 1
    assert queued[0]["platform"] == "slack"


async def test_send_im_message_with_live_connector_does_not_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.outbound import DeliveryReceipt
    from fleetent.tools.builtin_tools import send_im_message
    from fleetent.tools.registry import ToolContext

    connector = object()
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: (_ for _ in ()).throw(AssertionError("standalone must not enqueue")),
    )
    send_to = AsyncMock(
        return_value=DeliveryReceipt(
            ok=True,
            platform="slack",
            target="U_OTHER",
            target_type="user",
            kind="text",
        )
    )
    monkeypatch.setattr("fleetent.outbound.send_to", send_to)
    monkeypatch.setattr("fleetent.outbound.is_reachable", AsyncMock(return_value=True))

    ctx = ToolContext(
        agent_name="support",
        session_context=SessionContext(platform="slack", sender_id="U_SENDER"),
        outbound_connectors={"slack": connector},
    )

    result = await send_im_message(target="U_OTHER", text="hello", tool_context=ctx)

    assert "U_OTHER" in result
    assert send_to.await_count == 1


@pytest.fixture()
def _mock_loop_env(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    client = AsyncMock()
    cfg = MagicMock()
    cfg.model = "test-model"
    cfg.max_tokens = 512
    cfg.params = {}
    cfg.fallbacks = ()
    monkeypatch.setattr(
        loop_mod, "get_async_client_and_config", lambda *a, **kw: (client, cfg), raising=False
    )
    monkeypatch.setattr(loop_mod, "_build_async_client", lambda resolved, api_key: client)
    monkeypatch.setattr(loop_mod, "get_schemas", lambda: [])
    monkeypatch.setattr(loop_mod, "maybe_compress", lambda msgs, **kw: msgs)
    monkeypatch.setattr(loop_mod, "log_run", lambda *a, **kw: None)
    monkeypatch.setattr(loop_mod, "extract_and_update", AsyncMock())
    monkeypatch.setattr(loop_mod, "available_skills_prompt", lambda *a, **k: "")
    monkeypatch.setattr(
        loop_mod,
        "resolve_limits",
        lambda max_turns=None, max_consecutive_failures=None, config=None: (
            max_turns if max_turns is not None else 50,
            max_consecutive_failures if max_consecutive_failures is not None else 3,
        ),
    )
    return client


def _tool_response(tool_name: str, arguments: str) -> AsyncMock:
    tc = MagicMock()
    tc.id = f"tc-{tool_name}"
    tc.type = "function"
    tc.function.name = tool_name
    tc.function.arguments = arguments

    msg1 = MagicMock()
    msg1.content = None
    msg1.tool_calls = [tc]
    msg1.refusal = None
    choice1 = MagicMock()
    choice1.message = msg1
    choice1.finish_reason = "tool_calls"
    resp1 = MagicMock()
    resp1.choices = [choice1]
    resp1.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    msg2 = MagicMock()
    msg2.content = "done"
    msg2.tool_calls = None
    msg2.refusal = None
    choice2 = MagicMock()
    choice2.message = msg2
    choice2.finish_reason = "stop"
    resp2 = MagicMock()
    resp2.choices = [choice2]
    resp2.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)

    responses = [resp1, resp2]
    call_count = [0]

    async def _create(**kwargs):
        result = responses[call_count[0]]
        call_count[0] += 1
        return result

    return _create


async def test_loop_send_im_message_queues_when_node_managed(
    monkeypatch: pytest.MonkeyPatch, _mock_loop_env: MagicMock
) -> None:
    import fleetent.tools  # noqa: F401
    from fleetent.im_gateway.normalizer import SessionContext

    _enable_node_managed_env(monkeypatch)

    queued: list[dict[str, object]] = []
    monkeypatch.setattr(
        "fleetent.im_gateway.outbound_queue_store.enqueue",
        lambda **kwargs: queued.append(kwargs) or {"id": "q1"},
    )
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "none")
    _mock_loop_env.chat.completions.create = _tool_response(
        "send_im_message", '{"target":"U_OTHER","text":"hello"}'
    )

    await loop_mod.run(
        messages=[{"role": "user", "content": "ping U_OTHER"}],
        principal=MagicMock(user_id="u1", tenant_id="default"),
        reply_func=AsyncMock(),
        agent_name="support",
        outbound_connectors={},
        session_context=SessionContext(platform="slack", sender_id="U_SENDER"),
    )

    assert len(queued) == 1
    assert queued[0]["platform"] == "slack"
