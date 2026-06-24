from __future__ import annotations

import json
import re

import httpx

from tests.e2e._im_helpers import (
    TOOL_STUB_APPROVER,
    agent_state_db_path,
    configure_agent_for_im_approval,
    enqueue_directed_row,
    im_route_body,
    im_route_headers,
    managed_agent_route_server,
    point_support_agent_to_provider_base_url,
    read_queue_rows,
    tool_call_stub_server,
)
from tests.e2e._path_helpers import agent_home_dir
from tests.e2e._path_helpers import agent_state_db_path as e2e_agent_state_db_path
from tests.e2e.conftest import wait_for_condition


def test_im_route_replies_with_stub_text(managed_stack) -> None:
    configure_agent_for_im_approval(managed_stack)

    with managed_agent_route_server(managed_stack) as base_url:
        response = httpx.post(
            f"{base_url}/im/route",
            headers=im_route_headers(managed_stack, user_id="user-im-route"),
            json=im_route_body(
                text="hello inbound route",
                user_id="user-im-route",
                session_id="sess-im-route",
                agent_name=managed_stack.agent_name,
            ),
            timeout=10.0,
        )

        assert response.status_code == 200, response.text
    replies = response.json()["replies"]
    assert len(replies) == 1
    assert replies[0]["blocks"] is None
    assert replies[0]["text"].startswith("stub: [发送人 slack:user-im-route")
    assert "hello inbound route" in replies[0]["text"]


async def test_im_route_high_risk_tool_queues_approval_dm(managed_stack, monkeypatch) -> None:
    from fleetent import agent_config
    from fleetent.db import SQLiteDatabase
    from fleetent.governance import (
        approval_request_store,
        approval_store,
        tool_auto_approvals_store,
    )
    from fleetent.identity import Principal
    from fleetent.im_gateway import normalizer, outbound_queue_store
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
    from fleetent.outbound_connectors import resolve_for_runtime
    from fleetent.runtime import context as runtime_context
    from fleetent.runtime.agent_app import _redirect_agent_data_paths
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate
    from fleetent.session import index as session_index

    configure_agent_for_im_approval(managed_stack)
    agent_home = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name)
    state_db = e2e_agent_state_db_path(managed_stack.home_dir, managed_stack.agent_name)
    state_db_handle = SQLiteDatabase(path=state_db)
    migrate(state_db_handle, AGENT_STATE_MIGRATIONS)
    _redirect_agent_data_paths(agent_home)
    outbound_queue_store.set_state_db(state_db_handle)
    approval_store.set_state_db(state_db_handle)
    approval_request_store.set_state_db(state_db_handle)
    tool_auto_approvals_store.set_state_db(state_db_handle)
    runtime_context.set_state_db(state_db_handle)
    session_index.set_state_db(state_db_handle)
    monkeypatch.setenv("FLEETENT_NODE_ID", managed_stack.node_id)
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", managed_stack.platform_url)
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-e2e-test")
    monkeypatch.setenv("FLEETENT_AGENT_SUPPORT_MODEL", "sk-e2e-stub")

    with tool_call_stub_server(
        target="U_TARGET", text="please review this request"
    ) as provider_url:
        point_support_agent_to_provider_base_url(managed_stack, base_url=provider_url)
        agent_config.scan_home(agent_home)

        replies: list[str] = []

        async def _reply(text: str, blocks=None) -> None:
            del blocks
            replies.append(text)

        await normalizer.route(
            NormalizedMessage(
                platform="slack",
                session_id="sess-approval",
                user_id="user-approval",
                text="trigger outbound approval",
                attachments=[],
                reply_func=_reply,
                agent_name=managed_stack.agent_name,
                outbound_connectors=resolve_for_runtime(managed_stack.agent_name, {}),
                session_context=SessionContext(
                    platform="slack",
                    sender_id="user-approval",
                    sender_name="E2E User",
                    chat_type="dm",
                    channel_name="user-approval",
                ),
            ),
            principal=Principal(user_id="user-approval", tenant_id="default"),
        )

    assert replies

    row = wait_for_condition(
        lambda: _pending_approval_row(state_db),
        timeout=5.0,
        interval=0.1,
        description="approval dm queued",
    )
    address = json.loads(str(row["address_json"]))
    payload = json.loads(str(row["payload_json"]))

    assert row["platform"] == "slack"
    assert row["status"] == "pending"
    assert address == {
        "target": TOOL_STUB_APPROVER.split(":", 1)[1],
        "target_type": "user",
        "thread": None,
    }
    assert payload["kind"] == "text"
    assert "Approval ID:" in payload["text"]


async def test_im_route_approve_command_resumes_pending_run(managed_stack, monkeypatch) -> None:
    from fleetent import agent_config
    from fleetent.db import SQLiteDatabase
    from fleetent.governance import (
        approval_request_store,
        approval_store,
        tool_auto_approvals_store,
    )
    from fleetent.identity import Principal
    from fleetent.im_gateway import normalizer, outbound_queue_store
    from fleetent.im_gateway.normalizer import NormalizedMessage, SessionContext
    from fleetent.outbound_connectors import resolve_for_runtime
    from fleetent.runtime import context as runtime_context
    from fleetent.runtime.agent_app import _redirect_agent_data_paths
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate
    from fleetent.session import index as session_index

    configure_agent_for_im_approval(managed_stack)
    agent_home = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name)
    state_db = e2e_agent_state_db_path(managed_stack.home_dir, managed_stack.agent_name)
    state_db_handle = SQLiteDatabase(path=state_db)
    migrate(state_db_handle, AGENT_STATE_MIGRATIONS)
    _redirect_agent_data_paths(agent_home)
    outbound_queue_store.set_state_db(state_db_handle)
    approval_store.set_state_db(state_db_handle)
    approval_request_store.set_state_db(state_db_handle)
    tool_auto_approvals_store.set_state_db(state_db_handle)
    runtime_context.set_state_db(state_db_handle)
    session_index.set_state_db(state_db_handle)
    monkeypatch.setenv("FLEETENT_NODE_ID", managed_stack.node_id)
    monkeypatch.setenv("FLEETENT_NODE_PLATFORM_URL", managed_stack.platform_url)
    monkeypatch.setenv("FLEETENT_NODE_SERVICE_KEY", "ma-e2e-test")
    monkeypatch.setenv("FLEETENT_AGENT_SUPPORT_MODEL", "sk-e2e-stub")

    with tool_call_stub_server(
        target="U_TARGET", text="please review this request"
    ) as provider_url:
        point_support_agent_to_provider_base_url(managed_stack, base_url=provider_url)
        agent_config.scan_home(agent_home)

        replies: list[str] = []

        async def _reply(text: str, blocks=None) -> None:
            del blocks
            replies.append(text)

        await normalizer.route(
            NormalizedMessage(
                platform="slack",
                session_id="sess-approval-resume",
                user_id="user-approval",
                text="trigger outbound approval",
                attachments=[],
                reply_func=_reply,
                agent_name=managed_stack.agent_name,
                outbound_connectors=resolve_for_runtime(managed_stack.agent_name, {}),
                session_context=SessionContext(
                    platform="slack",
                    sender_id="user-approval",
                    sender_name="E2E User",
                    chat_type="dm",
                    channel_name="user-approval",
                ),
            ),
            principal=Principal(user_id="user-approval", tenant_id="default"),
        )

        row = wait_for_condition(
            lambda: _pending_approval_row(state_db),
            timeout=5.0,
            interval=0.1,
            description="approval dm queued for resume test",
        )
        approval_id = _approval_id_from_row(row)

        with managed_agent_route_server(managed_stack) as base_url:
            response = httpx.post(
                f"{base_url}/im/route",
                headers=im_route_headers(managed_stack, user_id="U_APPROVER", tenant_id="default"),
                json=im_route_body(
                    text=f"approve {approval_id}",
                    user_id="U_APPROVER",
                    session_id="sess-approval-command",
                    agent_name=managed_stack.agent_name,
                ),
                timeout=10.0,
            )

    assert response.status_code == 200, response.text
    replies = response.json()["replies"]
    assert len(replies) == 1
    assert replies[0]["blocks"] is None
    assert replies[0]["text"] == "stub: approval resumed"


def test_directed_queue_row_advances_after_user_binding_lookup(managed_stack) -> None:
    from fleetent.db import SQLiteDatabase
    from fleetent.platform import im_gateway_management
    from fleetent.runtime.agent_state_migrations import MIGRATIONS as AGENT_STATE_MIGRATIONS
    from fleetent.schema_migrations import migrate

    state_db = agent_state_db_path(managed_stack)
    migrate(SQLiteDatabase(path=state_db), AGENT_STATE_MIGRATIONS)
    user = im_gateway_management.resolve_or_provision(
        "default",
        verified_email="fanout@example.com",
        channel="slack",
        platform_user_id="U_FANOUT",
    )
    im_gateway_management.attach_identity("telegram", "TG_FANOUT", user.id)

    queue_id = enqueue_directed_row(
        state_db,
        user_id=user.id,
        text="fanout probe",
        dedup_key="directed-fanout-probe",
    )

    row = wait_for_condition(
        lambda: _queue_row_with_status(state_db, queue_id, "sent"),
        timeout=10.0,
        interval=0.2,
        description="directed queue row drained by node",
    )
    address = json.loads(str(row["address_json"]))
    payload = json.loads(str(row["payload_json"]))
    addresses = im_gateway_management.resolve_user_addresses(user.id)

    assert address == {"target_type": "user_id", "user_id": user.id}
    assert payload["kind"] == "text"
    assert payload["text"] == "fanout probe"
    assert row["status"] == "sent"
    assert {item["platform"] for item in addresses} == {"slack", "telegram"}


def _pending_approval_row(state_db) -> dict[str, str] | None:
    for row in reversed(read_queue_rows(state_db)):
        payload = json.loads(str(row["payload_json"]))
        if row["platform"] != "slack" or row["status"] != "pending":
            continue
        if not re.search(r"Approval ID: `[^`]+`", str(payload.get("text", ""))):
            continue
        return row
    return None


def _approval_id_from_row(row: dict[str, str]) -> str:
    payload = json.loads(str(row["payload_json"]))
    match = re.search(r"Approval ID: `([^`]+)`", str(payload.get("text", "")))
    assert match is not None
    return match.group(1)


def _queue_row_with_status(state_db, queue_id: str, status: str) -> dict[str, str] | None:
    for row in read_queue_rows(state_db):
        if row["id"] == queue_id and row["status"] == status:
            return row
    return None


def _existing_agent_state_db(managed_stack):
    path = agent_state_db_path(managed_stack)
    return path if path.exists() else None
