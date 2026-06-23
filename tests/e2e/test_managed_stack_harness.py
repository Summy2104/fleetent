from __future__ import annotations

import json

import httpx


def test_llm_stub_streams_deterministic_reply(llm_stub_base_url: str) -> None:
    with httpx.stream(
        "POST",
        f"{llm_stub_base_url}/chat/completions",
        json={
            "model": "stub-model",
            "stream": True,
            "messages": [{"role": "user", "content": "Say hello from the harness"}],
        },
        timeout=5.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    text = body.decode("utf-8")
    assert response.status_code == 200
    assert "data: " in text
    assert "stub: Say hello from the harness" in text
    assert "data: [DONE]" in text


def test_managed_stack_starts_platform_node_and_agent(managed_stack) -> None:
    assert managed_stack.platform_url.startswith("http://127.0.0.1:")
    assert managed_stack.node_id == "node-e2e"
    assert managed_stack.agent_name == "support"
    assert managed_stack.agent_status["phase"] == "running"
    assert managed_stack.agent_status["health"] == "healthy"


def test_managed_chat_ingress_streams_stub_reply(managed_stack) -> None:
    with httpx.stream(
        "POST",
        f"{managed_stack.platform_url}/admin/agents/{managed_stack.agent_name}/chat",
        headers=managed_stack.admin_session_headers,
        json={"message": "hello managed world"},
        timeout=10.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    text = body.decode("utf-8")
    assert response.status_code == 200, text
    assert "stub: hello managed world" in text


def test_node_lifecycle_fetches_desired_state_and_reports_running_agent(managed_stack) -> None:
    payload = json.loads(managed_stack.desired_state_cache_path.read_text(encoding="utf-8"))

    assert payload["node_id"] == managed_stack.node_id
    assert [agent["name"] for agent in payload["agents"]] == [managed_stack.agent_name]
    assert isinstance(managed_stack.agent_status["pid"], int)
    assert managed_stack.agent_status["health"] == "healthy"
