from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from fleetent import agent_store
from fleetent.agent_config import load_agent_file
from fleetent.identity import Principal, encode_ingress_principal
from fleetent.platform import im_gateway_management
from fleetent.platform.agent_lifecycle import materialize
from fleetent.platform.model_provider_management import provider_admin_store
from fleetent.platform.node_management import node_store
from tests.e2e._entrypoint_smoke import (
    child_env,
    repo_root,
    reserve_port,
    run_command,
    running_process,
)
from tests.e2e._path_helpers import (
    agent_home_dir,
)
from tests.e2e._path_helpers import (
    agent_state_db_path as tenant_agent_state_db_path,
)
from tests.e2e.conftest import ManagedStack, wait_for_condition

TOOL_STUB_PROVIDER_ID = "stub-provider"
TOOL_STUB_APPROVER = "slack:U_APPROVER"


class _ChatMessage(BaseModel):
    role: str
    content: str | None = None


class _ChatRequest(BaseModel):
    model: str
    messages: list[_ChatMessage] = Field(default_factory=list)
    stream: bool = False


tool_call_stub_app = FastAPI(title="fleetent-e2e-im-tool-stub")


@tool_call_stub_app.get("/health")
async def tool_stub_health() -> dict[str, str]:
    return {"status": "ok"}


@tool_call_stub_app.post("/v1/chat/completions")
async def tool_stub_chat(body: _ChatRequest) -> JSONResponse:
    target = os.environ["FLEETENT_E2E_TOOL_TARGET"]
    text = os.environ["FLEETENT_E2E_TOOL_TEXT"]
    tool_name = os.environ.get("FLEETENT_E2E_TOOL_NAME", "send_im_message")
    saw_tool_result = any(message.role == "tool" for message in body.messages)
    if saw_tool_result:
        message = {"role": "assistant", "content": "stub: approval resumed"}
        finish_reason = "stop"
    else:
        message = {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call-send-im-message",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": json.dumps(
                            {"target": target, "text": text},
                            ensure_ascii=True,
                            separators=(",", ":"),
                        ),
                    },
                }
            ],
        }
        finish_reason = "tool_calls"
    return JSONResponse(
        {
            "id": "chatcmpl-tool-stub",
            "object": "chat.completion",
            "model": body.model,
            "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
        }
    )


def agent_state_db_path(managed_stack: ManagedStack) -> Path:
    return tenant_agent_state_db_path(managed_stack.home_dir, managed_stack.agent_name)


def read_queue_rows(db_path: Path) -> list[dict[str, Any]]:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, platform, address_json, payload_json, dedup_key, status, attempts, "
            "created_at, sent_at FROM im_outbound_queue ORDER BY created_at ASC, id ASC"
        ).fetchall()
    return [dict(row) for row in rows]


def read_queue_row(db_path: Path, queue_id: str) -> dict[str, Any] | None:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, platform, address_json, payload_json, dedup_key, status, attempts, "
            "created_at, sent_at FROM im_outbound_queue WHERE id = :id",
            {"id": queue_id},
        ).fetchone()
    return None if row is None else dict(row)


def enqueue_directed_row(db_path: Path, *, user_id: str, text: str, dedup_key: str) -> str:
    row = {
        "id": dedup_key,
        "platform": "directed",
        "address_json": json.dumps(
            {"target_type": "user_id", "user_id": user_id},
            ensure_ascii=False,
            sort_keys=True,
        ),
        "payload_json": json.dumps(
            {"kind": "text", "text": text, "blocks": []},
            ensure_ascii=False,
            sort_keys=True,
        ),
        "dedup_key": dedup_key,
        "status": "pending",
        "attempts": 0,
    }
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "INSERT INTO im_outbound_queue ("
            "id, platform, address_json, payload_json, dedup_key, status, attempts, created_at, "
            "sent_at"
            ") VALUES ("
            ":id, :platform, :address_json, :payload_json, :dedup_key, :status, :attempts, "
            "datetime('now'), NULL"
            ")",
            row,
        )
        conn.commit()
    return str(row["id"])


def current_agent_status(managed_stack: ManagedStack) -> dict[str, Any] | None:
    for row in node_store.list_agent_status_by_node(managed_stack.node_id):
        if int(row["agent_id"]) == managed_stack.agent_id and row.get("health") == "healthy":
            return dict(row)
    return None


def wait_for_agent_healthy(
    managed_stack: ManagedStack, *, old_pid: int | None = None, timeout: float = 30.0
) -> dict[str, Any]:
    def _probe() -> dict[str, Any] | None:
        status = current_agent_status(managed_stack)
        if status is None:
            return None
        if old_pid is not None and int(status["pid"]) == old_pid:
            return None
        return status

    return wait_for_condition(
        _probe,
        timeout=timeout,
        interval=0.5,
        description="agent healthy after config change",
    )


def wait_for_agent_home_text(
    managed_stack: ManagedStack, *, pattern: str, timeout: float = 30.0
) -> str:
    agent_yaml = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name) / "agent.yaml"

    def _probe() -> str | None:
        if not agent_yaml.exists():
            return None
        text = agent_yaml.read_text(encoding="utf-8")
        return text if pattern in text else None

    return wait_for_condition(
        _probe,
        timeout=timeout,
        interval=0.5,
        description=f"agent home contains {pattern!r}",
    )


def wait_for_desired_state_text(
    managed_stack: ManagedStack, *, pattern: str, timeout: float = 30.0
) -> str:
    def _probe() -> str | None:
        if not managed_stack.desired_state_cache_path.exists():
            return None
        text = managed_stack.desired_state_cache_path.read_text(encoding="utf-8")
        return text if pattern in text else None

    return wait_for_condition(
        _probe,
        timeout=timeout,
        interval=0.5,
        description=f"desired-state cache contains {pattern!r}",
    )


def wait_for_agent_http_ready(managed_stack: ManagedStack, *, timeout: float = 30.0) -> None:
    def _probe() -> bool | None:
        try:
            response = httpx.get(f"{agent_base_url(managed_stack)}/health", timeout=0.5)
        except Exception:
            return None
        return True if response.status_code == 200 else None

    wait_for_condition(
        _probe,
        timeout=timeout,
        interval=0.5,
        description="agent health endpoint ready",
    )


def restart_managed_agent(managed_stack: ManagedStack) -> None:
    agent_home = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name)
    result = run_command(
        [
            sys.executable,
            "-m",
            "fleetent",
            "agent",
            "stop",
            managed_stack.agent_name,
            "--home",
            str(agent_home),
        ],
        env=child_env(extra={}),
        cwd=repo_root(),
    )
    if result.returncode not in (0, 1):
        raise AssertionError(
            f"managed agent stop failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )


def find_agent_gateway_port(managed_stack: ManagedStack) -> int:
    home = str(agent_home_dir(managed_stack.home_dir, managed_stack.agent_name))
    result = subprocess.run(
        ["ps", "ax", "-o", "pid=,command="],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise AssertionError(f"ps failed while probing agent port: {result.stderr}")
    matches: list[tuple[int, list[str]]] = []
    for line in result.stdout.splitlines():
        if "<defunct>" in line or "fleetent agent run" not in line or home not in line:
            continue
        parts = line.strip().split()
        if not parts:
            continue
        pid = int(parts[0])
        argv = parts[1:]
        matches.append((pid, argv))
    for _pid, argv in sorted(matches, key=lambda item: item[0], reverse=True):
        for index, part in enumerate(argv):
            if part == "--port" and index + 1 < len(argv):
                return int(argv[index + 1])
    raise AssertionError(f"could not discover gateway port for {home}:\n{result.stdout}")


def agent_base_url(managed_stack: ManagedStack) -> str:
    return f"http://127.0.0.1:{find_agent_gateway_port(managed_stack)}"


def _agent_tui_token(managed_stack: ManagedStack) -> str:
    env_path = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name) / ".env"
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("FLEETENT_TUI_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise AssertionError(f"could not find FLEETENT_TUI_TOKEN in {env_path}")


def im_route_headers(
    managed_stack: ManagedStack, *, user_id: str, tenant_id: str = "default"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_agent_tui_token(managed_stack)}",
        "Content-Type": "application/json",
        "X-Fleetent-Principal": encode_ingress_principal(
            Principal(user_id=user_id, tenant_id=tenant_id)
        ),
    }


def im_route_body(
    *,
    text: str,
    user_id: str,
    session_id: str,
    agent_name: str = "support",
    platform: str = "slack",
) -> dict[str, Any]:
    return {
        "platform": platform,
        "session_id": session_id,
        "user_id": user_id,
        "text": text,
        "agent_name": agent_name,
        "channel_id": "",
        "workspace_id": "T_E2E",
        "attachments": [],
        "session_context": {
            "platform": platform,
            "sender_id": user_id,
            "sender_name": "E2E User",
            "chat_type": "dm",
            "channel_name": user_id,
            "was_mentioned": False,
            "thread_root": "",
        },
    }


@contextlib.contextmanager
def managed_agent_route_server(managed_stack: ManagedStack) -> Iterator[str]:
    port = reserve_port()
    agent_home = agent_home_dir(managed_stack.home_dir, managed_stack.agent_name)
    argv = [
        sys.executable,
        "-m",
        "fleetent",
        "agent",
        "run",
        managed_stack.agent_name,
        "--no-im",
        "--port",
        str(port),
        "--home",
        str(agent_home),
    ]
    env = child_env(
        extra={
            "DATABASE_URL": os.environ["DATABASE_URL"],
            "FLEETENT_HOME": str(agent_home),
            "FLEETENT_SECRET_KEY": os.environ["FLEETENT_SECRET_KEY"],
            "FLEETENT_NODE_ID": managed_stack.node_id,
            "FLEETENT_NODE_PLATFORM_URL": managed_stack.platform_url,
            "FLEETENT_NODE_SERVICE_KEY": "ma-e2e-test",
            "FLEETENT_AGENT_SUPPORT_MODEL": "sk-e2e-stub",
        }
    )
    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_condition(
            lambda: _http_ready(f"http://127.0.0.1:{port}/health"),
            timeout=20.0,
            interval=0.2,
            description="temporary managed agent route server ready",
        )
        try:
            yield f"http://127.0.0.1:{port}"
        finally:
            if proc.poll() is None:
                proc.terminate()


def configure_agent_for_im_approval(managed_stack: ManagedStack) -> dict[str, Any]:
    agent_store.set_im_capabilities(
        managed_stack.agent_id, supports_dm=True, supports_groups=False
    )
    agent_store.set_config_overrides(
        managed_stack.agent_name,
        {
            "allowed_tools": ["send_im_message"],
            "im": {
                "slack": {
                    "bot_token_env": "FLEETENT_FAKE_SLACK_BOT_TOKEN",
                    "app_token_env": "FLEETENT_FAKE_SLACK_APP_TOKEN",
                    "access": {"allow_all_users": True, "require_approval": False},
                }
            },
            "approval": {
                "by_risk": {"medium": {"approvers": [TOOL_STUB_APPROVER], "policy": "any"}}
            },
        },
    )
    materialize.materialize_from_store(managed_stack.agent_name)
    wait_for_agent_home_text(managed_stack, pattern="FLEETENT_FAKE_SLACK_BOT_TOKEN", timeout=30.0)
    materialized = load_agent_file(agent_home_dir(managed_stack.home_dir, managed_stack.agent_name))
    assert materialized.im.supports_dm is True
    assert materialized.im.slack is not None
    assert materialized.im.slack.access.allow_all_users is True
    restart_managed_agent(managed_stack)
    wait_for_agent_http_ready(managed_stack, timeout=30.0)
    return current_agent_status(managed_stack) or {}


def point_support_agent_to_provider_base_url(
    managed_stack: ManagedStack, *, base_url: str
) -> dict[str, Any]:
    provider_admin_store.edit_provider(TOOL_STUB_PROVIDER_ID, base_url=base_url)
    materialize.materialize_from_store(managed_stack.agent_name)
    wait_for_agent_home_text(managed_stack, pattern=base_url, timeout=30.0)
    restart_managed_agent(managed_stack)
    wait_for_agent_http_ready(managed_stack, timeout=30.0)
    return current_agent_status(managed_stack) or {}


def bind_user_im_address(
    *, tenant_id: str, user_id: str, platform: str, platform_user_id: str
) -> None:
    existing = im_gateway_management.resolve_user_addresses(user_id)
    if any(
        row.get("platform") == platform and row.get("platform_user_id") == platform_user_id
        for row in existing
    ):
        return
    mapped = im_gateway_management.get_mapped_user(platform, platform_user_id)
    if mapped is None:
        im_gateway_management.attach_identity(platform, platform_user_id, user_id)
        return
    if mapped.id != user_id:
        raise AssertionError(
            f"platform identity {platform}:{platform_user_id} already mapped to {mapped.id}"
        )


@contextlib.contextmanager
def tool_call_stub_server(
    *, target: str, text: str, tool_name: str = "send_im_message"
) -> Iterator[str]:
    port = reserve_port()
    argv = [
        sys.executable,
        "-m",
        "uvicorn",
        "tests.e2e._im_helpers:tool_call_stub_app",
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--log-level",
        "warning",
    ]
    env = child_env(
        extra={
            "FLEETENT_E2E_TOOL_TARGET": target,
            "FLEETENT_E2E_TOOL_TEXT": text,
            "FLEETENT_E2E_TOOL_NAME": tool_name,
        }
    )
    with running_process(argv, env=env, cwd=repo_root()) as proc:
        wait_for_condition(
            lambda: _tool_stub_ready(port),
            timeout=10.0,
            interval=0.2,
            description="tool-call stub ready",
        )
        try:
            yield f"http://127.0.0.1:{port}/v1"
        finally:
            if proc.poll() is None:
                proc.terminate()


def _tool_stub_ready(port: int) -> bool | None:
    try:
        response = httpx.get(f"http://127.0.0.1:{port}/health", timeout=0.5)
    except httpx.HTTPError:
        return None
    return True if response.status_code == 200 else None


def _http_ready(url: str) -> bool | None:
    try:
        response = httpx.get(url, timeout=0.5)
    except httpx.HTTPError:
        return None
    return True if response.status_code == 200 else None
