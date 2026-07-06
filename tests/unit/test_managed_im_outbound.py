"""Managed == standalone outbound: agent self-hosts its IM connection (agent-hosted-im).

After the unification there is no queue-backed ManagedOutboundConnector: a healthy managed
runtime has a live process-local connector exactly like standalone, and every outbound path
(reply / send_im_message / approval) sends directly. These tests assert the direct-send path
is taken and that no legacy enqueue seam is consulted.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

import fleetent.runtime.loop as loop_mod


def _enable_node_managed_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # agent-hosted-im: managed is signalled by the single delivered loopback URL.
    monkeypatch.setenv("FLEETENT_NODE_LOOPBACK_URL", "http://127.0.0.1:8790")


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


def test_managed_outbound_connector_is_removed() -> None:
    """The queue-backed proxy is gone (agent-hosted-im full cutover)."""
    import fleetent.outbound_connectors as oc

    assert not hasattr(oc, "ManagedOutboundConnector")


async def test_start_scheduler_resolver_uses_live_connectors_from_registry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.im_gateway import connector_registry
    from fleetent.runtime import agent_app

    _enable_node_managed_env(monkeypatch)

    live = object()
    monkeypatch.setattr(connector_registry, "snapshot", lambda name: {"slack": live})

    captured: dict[str, object] = {}

    def _fake_ctor(settings=None, connectors_resolver=None):  # type: ignore[no-untyped-def]
        captured["resolver"] = connectors_resolver
        inst = MagicMock()
        inst.start = AsyncMock()
        return inst

    monkeypatch.setattr("fleetent.cron_scheduler.CronScheduler", _fake_ctor)

    await agent_app._start_scheduler(_agent(enabled=True, name="support"))

    resolved = captured["resolver"]()
    # Live connector registered by the agent's own supervisor is used directly — no proxy.
    assert resolved == {"slack": live}


@pytest.fixture(autouse=True)
def _mock_approval_store(monkeypatch: pytest.MonkeyPatch) -> None:
    from fleetent.governance import approval_store, tool_auto_approvals_store

    monkeypatch.setattr(approval_store, "insert_approval", MagicMock())
    monkeypatch.setattr(approval_store, "update_approval", MagicMock())
    monkeypatch.setattr(tool_auto_approvals_store, "is_allowed", MagicMock(return_value=False))


async def test_send_im_message_with_live_connector_sends_directly(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.outbound import DeliveryReceipt
    from fleetent.tools.builtin_tools import send_im_message
    from fleetent.tools.registry import ToolContext

    # Managed or standalone: with a live connector present the send is direct.
    _enable_node_managed_env(monkeypatch)

    connector = object()
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
    monkeypatch.setattr(loop_mod, "run_pipeline_from_conversation", AsyncMock())
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


async def test_loop_send_im_message_sends_directly_when_managed_with_live_connector(
    monkeypatch: pytest.MonkeyPatch, _mock_loop_env: MagicMock
) -> None:
    import fleetent.tools  # noqa: F401
    from fleetent.im_gateway.normalizer import SessionContext
    from fleetent.outbound import DeliveryReceipt

    _enable_node_managed_env(monkeypatch)

    send_to = AsyncMock(
        return_value=DeliveryReceipt(
            ok=True, platform="slack", target="U_OTHER", target_type="user", kind="text"
        )
    )
    monkeypatch.setattr("fleetent.outbound.send_to", send_to)
    monkeypatch.setattr("fleetent.outbound.is_reachable", AsyncMock(return_value=True))
    monkeypatch.setattr(loop_mod, "evaluate_risk_level", lambda name, args, ctx: "none")
    _mock_loop_env.chat.completions.create = _tool_response(
        "send_im_message", '{"target":"U_OTHER","text":"hello"}'
    )

    connector = object()
    await loop_mod.run(
        messages=[{"role": "user", "content": "ping U_OTHER"}],
        principal=MagicMock(user_id="u1", tenant_id="default"),
        reply_func=AsyncMock(),
        agent_name="support",
        outbound_connectors={"slack": connector},
        session_context=SessionContext(platform="slack", sender_id="U_SENDER"),
    )

    assert send_to.await_count == 1
