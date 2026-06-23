from __future__ import annotations

import httpx
import respx

from fleetent.node.config import NodeConfig
from fleetent.node.provider import DesiredAgent, DesiredState


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _home(tmp_path, agent_name: str = "support", tenant_id: str = "tenant-1"):
    return tmp_path / "tenants" / tenant_id / "agents" / agent_name


# ---------------------------------------------------------------------------
# Task 2.1 / 2.2 — PlatformAddressResolver
# ---------------------------------------------------------------------------


@respx.mock
def test_platform_address_resolver_returns_all_bindings(tmp_path) -> None:
    from fleetent.node.im_edge import PlatformAddressResolver

    route = respx.post("https://platform.internal/nodes/node-a/identity/addresses").mock(
        return_value=httpx.Response(
            200,
            json={
                "addresses": [
                    {"platform": "slack", "platform_user_id": "U_alice"},
                    {"platform": "telegram", "platform_user_id": "TG_alice"},
                ]
            },
        )
    )
    resolver = PlatformAddressResolver(_config(tmp_path))

    addresses = resolver.resolve("user-42")

    assert addresses == [
        {"platform": "slack", "platform_user_id": "U_alice"},
        {"platform": "telegram", "platform_user_id": "TG_alice"},
    ]
    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer ma-" + "1" * 64
    assert b'"user_id":"user-42"' in request.content


@respx.mock
def test_platform_address_resolver_returns_empty_for_unbound_user(tmp_path) -> None:
    from fleetent.node.im_edge import PlatformAddressResolver

    respx.post("https://platform.internal/nodes/node-a/identity/addresses").mock(
        return_value=httpx.Response(200, json={"addresses": []})
    )
    resolver = PlatformAddressResolver(_config(tmp_path))

    addresses = resolver.resolve("user-unbound")

    assert addresses == []


@respx.mock
def test_platform_identity_resolver_calls_node_identity_endpoint(tmp_path) -> None:
    from fleetent.node.im_edge import PlatformIdentityResolver

    route = respx.post("https://platform.internal/nodes/node-a/identity/resolve").mock(
        return_value=httpx.Response(200, json={"user_id": "user-42", "tenant_id": "tenant-1"})
    )
    resolver = PlatformIdentityResolver(_config(tmp_path))
    resolver.update_agents({"support": "tenant-1"})

    user_id = resolver("support", "slack", "U123")

    assert user_id == "user-42"
    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer " + "ma-" + "1" * 64
    assert request.content == (
        b'{"tenant_id":"tenant-1","channel":"slack","platform_user_id":"U123"}'
    )


def test_node_im_edge_host_reconciles_materialized_bindings(tmp_path) -> None:
    from fleetent.node.im_edge import NodeIMEdgeHost

    class FakeSupervisor:
        def __init__(self) -> None:
            self.calls: list[dict[str, dict[str, str]]] = []

        async def reload_bindings(self, bindings: dict[str, dict[str, str]]) -> None:
            self.calls.append(bindings)

        async def stop_all(self) -> None:
            return None

    injected_resolvers = []
    slack_supervisor = FakeSupervisor()
    telegram_supervisor = FakeSupervisor()
    host = NodeIMEdgeHost(
        _config(tmp_path),
        slack_supervisor=slack_supervisor,
        telegram_supervisor=telegram_supervisor,
        resolver_setter=injected_resolvers.append,
    )

    host.reconcile(
        DesiredState(
            node_id="node-a",
            agents=[
                DesiredAgent(
                    agent_id=101,
                    name="support",
                    tenant_id="tenant-1",
                    config={
                        "name": "support",
                        "tenant_id": "tenant-1",
                        "im": {
                            "slack": {
                                "bot_token_env": "SLACK_BOT",
                                "app_token_env": "SLACK_APP",
                            },
                            "telegram": {
                                "bot_token_env": "TG_BOT",
                            },
                        },
                    },
                    secrets={
                        "SLACK_BOT": "xoxb-test",
                        "SLACK_APP": "xapp-test",
                        "TG_BOT": "123:abc",
                    },
                )
            ],
        )
    )

    assert len(injected_resolvers) == 1
    assert slack_supervisor.calls == [
        {"support": {"bot_token": "xoxb-test", "app_token": "xapp-test"}}
    ]
    assert telegram_supervisor.calls == [{"support": {"bot_token": "123:abc"}}]

    host.close()


async def test_node_im_edge_host_forwards_managed_reply_back_to_connector(tmp_path) -> None:
    from fleetent.im_gateway.normalizer import NormalizedMessage
    from fleetent.node.im_edge import NodeIMEdgeHost

    class FakeBackend:
        def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
            assert agent_name == "support"
            assert tenant_id == "tenant-1"
            return 9011

    dispatcher_holder: list[object] = []
    home = _home(tmp_path)
    home.mkdir(parents=True)
    (home / ".env").write_text("FLEETENT_TUI_TOKEN=ma-agent-token\n", encoding="utf-8")
    host = NodeIMEdgeHost(
        _config(tmp_path),
        backend=FakeBackend(),
        dispatcher_setter=lambda fn: dispatcher_holder.append(fn),
    )
    host.reconcile(
        DesiredState(
            node_id="node-a",
            agents=[
                DesiredAgent(
                    agent_id=101,
                    name="support",
                    tenant_id="tenant-1",
                    config={"name": "support", "tenant_id": "tenant-1"},
                    secrets={},
                )
            ],
        )
    )
    replies: list[str] = []

    async def fake_reply(text: str, blocks=None) -> None:
        replies.append(text)

    msg = NormalizedMessage(
        platform="telegram",
        session_id="session-1",
        user_id="u-real",
        text="hello",
        attachments=[],
        reply_func=fake_reply,
        agent_name="support",
        session_context=None,
    )

    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, json={"replies": [{"text": "managed reply"}]})
    )
    original_async_client = httpx.AsyncClient

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = FakeAsyncClient
    try:
        dispatcher = dispatcher_holder[-1]
        assert callable(dispatcher)
        await dispatcher(msg)
    finally:
        httpx.AsyncClient = original_async_client
        host.close()

    assert replies == ["managed reply"]


async def test_node_im_edge_host_intercepts_link_command_before_forwarding(tmp_path) -> None:
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
    from fleetent.node.im_edge import NodeIMEdgeHost

    class FakeBackend:
        def gateway_port(self, agent_name: str, tenant_id: str = "default") -> int | None:
            raise AssertionError(f"/link must not reach agent gateway for {agent_name}")

    dispatcher_holder: list[object] = []
    replies: list[str] = []
    host = NodeIMEdgeHost(
        _config(tmp_path),
        backend=FakeBackend(),
        dispatcher_setter=lambda fn: dispatcher_holder.append(fn),
    )

    async def fake_reply(text: str, blocks=None) -> None:
        replies.append(text)

    msg = NormalizedMessage(
        platform="telegram",
        session_id="session-1",
        user_id="u-standalone",
        text="/link abc123",
        attachments=[],
        reply_func=fake_reply,
        agent_name="support",
        session_context=SessionContext(
            platform="telegram",
            sender_id="424242",
            sender_name="Alice",
            chat_type="dm",
            channel_name="424242",
            was_mentioned=False,
            thread_root="",
        ),
    )

    requests: list[httpx.Request] = []
    transport = httpx.MockTransport(
        lambda request: (
            requests.append(request),
            httpx.Response(
                200, json={"status": "linked", "user_id": "user-42", "tenant_id": "tenant-1"}
            ),
        )[1]
    )
    original_async_client = httpx.AsyncClient

    class FakeAsyncClient(httpx.AsyncClient):
        def __init__(self, *args, **kwargs) -> None:
            kwargs["transport"] = transport
            super().__init__(*args, **kwargs)

    httpx.AsyncClient = FakeAsyncClient
    try:
        dispatcher = dispatcher_holder[-1]
        assert callable(dispatcher)
        await dispatcher(msg)
    finally:
        httpx.AsyncClient = original_async_client
        host.close()

    assert replies == ["Linked telegram account to your web identity."]
    assert len(requests) == 1
    assert requests[0].url.path == "/nodes/node-a/link-confirm"
