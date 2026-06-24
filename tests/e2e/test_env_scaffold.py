"""E2E: node reconcile creates .env scaffold for freshly pinned agents.

Regression test for: node _write_home must call ensure_env_scaffold so that
forwarder/IM-edge can always find FLEETENT_TUI_TOKEN without 503 errors.
"""

from __future__ import annotations

import httpx

from tests.e2e._entrypoint_smoke import wait_for_condition
from tests.e2e._path_helpers import agent_home_dir


def test_env_scaffold_created_for_freshly_pinned_agent(managed_stack) -> None:
    """Pin a new agent without calling materialize.write_home first.

    Node reconcile must create the .env with FLEETENT_TUI_TOKEN via _write_home,
    and the agent must be reachable via the platform chat API (no 503
    'has no env scaffold').
    """
    from fleetent import agent_store
    from fleetent.platform.agent_lifecycle import credential_slots, secret_store
    from fleetent.platform.node_management import node_store, placement_store

    # Create agent with same stub model as the existing support agent.
    fresh = agent_store.create_agent(
        "fresh-bot",
        "Fresh agent for env scaffold test.",
        [],
        model_overrides={"default": [{"provider_id": "stub-provider"}]},
    )
    credential_slots.ensure_slot(
        fresh,
        "env:FLEETENT_AGENT_SUPPORT_MODEL",
        mode="inject",
        env_name="FLEETENT_AGENT_SUPPORT_MODEL",
    )
    secret_store.set(fresh.id, "FLEETENT_AGENT_SUPPORT_MODEL", "sk-e2e-stub", "e2e")

    # Pin WITHOUT calling materialize.write_home — this is the bug scenario:
    # _write_home was the only code path triggered by node reconcile, and it
    # previously did not scaffold .env, leaving the agent unreachable.
    placement_store.pin_agent(fresh.id, managed_stack.node_id)

    # Node reconcile (interval=1s) should create .env via ensure_env_scaffold
    # inside _write_home before spawning the agent process.
    env_path = agent_home_dir(managed_stack.home_dir, "fresh-bot") / ".env"
    # wait_for_condition expects None when not-yet-ready; False would return immediately.
    wait_for_condition(
        lambda: env_path.exists() or None,
        timeout=30.0,
        interval=0.5,
        description="fresh agent .env scaffold created by node reconcile",
    )

    lines = dict(
        line.split("=", 1)
        for line in env_path.read_text(encoding="utf-8").strip().splitlines()
        if "=" in line
    )
    assert lines.get("FLEETENT_TUI_TOKEN", "").startswith("ma-")
    assert len(lines["FLEETENT_TUI_TOKEN"]) == 67

    # Wait for the agent to be running and healthy before testing chat.
    def _healthy() -> bool | None:
        for row in node_store.list_agent_status_by_node(managed_stack.node_id):
            if int(row["agent_id"]) == fresh.id and row.get("health") == "healthy":
                return True
        return None

    wait_for_condition(_healthy, timeout=30.0, interval=0.5, description="fresh agent healthy")

    # Forwarder must NOT return 503 "has no env scaffold".
    # Any other error (e.g. 401 from node-key auth issues) is acceptable — the spec
    # only requires the env scaffold to be present so the forwarder can find the token.
    with httpx.stream(
        "POST",
        f"{managed_stack.platform_url}/admin/agents/fresh-bot/chat",
        headers=managed_stack.admin_session_headers,
        json={"message": "hello fresh-bot"},
        timeout=15.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    text = body.decode("utf-8", errors="replace")
    assert b"has no env scaffold" not in body, (
        f"Forwarder returned 503 'has no env scaffold'. "
        f"Status={response.status_code} Body={text[:400]}"
    )
