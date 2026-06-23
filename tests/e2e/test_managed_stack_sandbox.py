"""E2E: run_code executes in Docker sandbox and folds output back to chat reply.

Probe result (task 1.1): skip if Docker daemon not reachable — sandbox is optional.
Probe result (task 1.2): stub must emit a streaming run_code tool-call; implemented
in _llm_stub.py via the "sandbox_trigger" keyword branch.
"""

from __future__ import annotations

import subprocess

import httpx
import pytest

from tests.e2e.conftest import ManagedStack


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "version"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return False


def test_run_code_executes_in_sandbox_and_folds_output_to_reply(
    managed_stack: ManagedStack,
) -> None:
    if not _docker_available():
        pytest.skip("Docker daemon not available — sandbox e2e skipped")

    with httpx.stream(
        "POST",
        f"{managed_stack.platform_url}/admin/agents/{managed_stack.agent_name}/chat",
        headers=managed_stack.admin_session_headers,
        json={"message": "sandbox_trigger: please run 2+2"},
        timeout=60.0,
    ) as response:
        body = b"".join(response.iter_bytes())

    text = body.decode("utf-8", errors="replace")
    assert response.status_code == 200, f"chat request failed:\n{text}"
    # Stub returns final reply with sandbox stdout; print(2+2) produces "4"
    assert "4" in text, f"expected '4' (sandbox stdout) in reply, got:\n{text}"
