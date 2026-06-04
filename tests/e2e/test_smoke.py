#!/usr/bin/env python3
"""
Smoke tests for fleetent. Requires a running server with ANTHROPIC_API_KEY set.

Usage:
  uv run python tests/e2e/test_smoke.py                        # auto-creates test user
  FLEETENT_TEST_KEY=ma-xxx uv run python tests/e2e/test_smoke.py   # use existing key
  FLEETENT_BASE_URL=http://host:8765 uv run python tests/e2e/test_smoke.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import suppress

import httpx
import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("FLEETENT_RUN_E2E") != "1",
    reason="set FLEETENT_RUN_E2E=1 and start the service to run smoke e2e tests",
)

BASE_URL = os.getenv("FLEETENT_BASE_URL", "http://localhost:8765")

# ── ANSI colours ──────────────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
RESET = "\033[0m"
BOLD = "\033[1m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {YELLOW}·{RESET} {msg}")


# ── helpers ───────────────────────────────────────────────────────────────────


def parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        if line.startswith("data: "):
            with suppress(json.JSONDecodeError):
                events.append(json.loads(line[6:]))
    return events


def done_content(events: list[dict]) -> str | None:
    for e in events:
        if e.get("type") == "done":
            return e.get("content", "")
    return None


def tool_calls(events: list[dict]) -> list[str]:
    return [e["name"] for e in events if e.get("type") == "tool_call"]


def chat(client: httpx.Client, message: str, timeout: int = 30) -> list[dict]:
    resp = client.post("/chat", json={"message": message}, timeout=timeout)
    resp.raise_for_status()
    return parse_sse(resp.text)


# ── setup: get or create test user ───────────────────────────────────────────


def get_api_key() -> str:
    key = os.getenv("FLEETENT_TEST_KEY")
    if key:
        info(f"Using existing key from FLEETENT_TEST_KEY ({key[:12]}...)")
        return key

    info("Creating smoke-test user via fleetent-admin...")
    result = subprocess.run(
        ["uv", "run", "fleetent-admin", "create-user", "--name", "smoke-test"],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"{RED}Failed to create test user:{RESET}\n{result.stderr}")
        sys.exit(1)

    for line in result.stdout.splitlines():
        if "api_key:" in line:
            key = line.split("api_key:")[1].strip().split()[0]
            info(f"Created test user, key: {key[:12]}...")
            return key

    print(f"{RED}Could not parse api_key from admin output:{RESET}\n{result.stdout}")
    sys.exit(1)


@pytest.fixture
def client() -> Iterator[httpx.Client]:
    api_key = get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}
    with httpx.Client(base_url=BASE_URL, headers=headers) as test_client:
        yield test_client


# ── test cases ────────────────────────────────────────────────────────────────


def run_test(name: str, fn) -> bool:
    print(f"\n{BOLD}{name}{RESET}")
    try:
        fn()
        return True
    except AssertionError as e:
        fail(str(e) if str(e) else "assertion failed")
        return False
    except Exception as e:
        fail(f"{type(e).__name__}: {e}")
        return False


def test_health(_client: httpx.Client) -> None:
    resp = httpx.get(f"{BASE_URL}/health", timeout=5)
    assert resp.status_code == 200, f"expected 200, got {resp.status_code}"
    data = resp.json()
    assert data["status"] == "ok", f"status={data['status']}"
    assert "adapters" in data
    ok(f"status=ok, adapters={data['adapters']}")


def test_invalid_key(_client: httpx.Client) -> None:
    resp = httpx.post(
        f"{BASE_URL}/chat",
        headers={"Authorization": "Bearer invalid-key"},
        json={"message": "hi"},
        timeout=5,
    )
    assert resp.status_code == 401, f"expected 401, got {resp.status_code}"
    ok("returns 401 for invalid key")


def test_basic_chat(client: httpx.Client) -> None:
    events = chat(client, "请用一句话回复：你好")
    content = done_content(events)
    assert content is not None, "no done event"
    assert len(content) > 0, "empty reply"
    ok(f"reply: {content[:60]}...")


def test_calculate_tool(client: httpx.Client) -> None:
    events = chat(client, "帮我计算 7 乘以 8，只告诉我结果")
    tools = tool_calls(events)
    assert "calculate" in tools, f"calculate not called, tools={tools}"
    content = done_content(events) or ""
    assert "56" in content, f"result '56' not in reply: {content}"
    ok("calculate called → reply contains '56'")


def test_get_time_tool(client: httpx.Client) -> None:
    events = chat(client, "现在几点了？")
    tools = tool_calls(events)
    assert "get_current_time" in tools, f"get_current_time not called, tools={tools}"
    content = done_content(events) or ""
    assert len(content) > 0
    ok(f"get_current_time called → {content[:50]}...")


def test_read_file_tool(client: httpx.Client) -> None:
    events = chat(client, "帮我读一下 README.md 文件的内容")
    tools = tool_calls(events)
    assert "read_file" in tools, f"read_file not called, tools={tools}"
    ok("read_file called")


def test_session_memory(client: httpx.Client) -> None:
    chat(client, "我的幸运数字是 42，请记住")
    time.sleep(0.5)
    events = chat(client, "我的幸运数字是多少？")
    content = done_content(events) or ""
    assert "42" in content, f"'42' not found in reply: {content}"
    ok("session memory works → reply contains '42'")


# ── main ──────────────────────────────────────────────────────────────────────

TESTS = [
    ("Health check", test_health),
    ("Invalid API key", test_invalid_key),
    ("Basic chat", test_basic_chat),
    ("Tool: calculate", test_calculate_tool),
    ("Tool: get_time", test_get_time_tool),
    ("Tool: read_file", test_read_file_tool),
    ("Session memory", test_session_memory),
]


def main() -> None:
    print(f"\n{BOLD}fleetent smoke tests{RESET} → {BASE_URL}\n")

    api_key = get_api_key()
    headers = {"Authorization": f"Bearer {api_key}"}

    passed = 0
    failed = 0

    with httpx.Client(base_url=BASE_URL, headers=headers) as client:
        for name, fn in TESTS:
            success = run_test(name, lambda f=fn: f(client))
            if success:
                passed += 1
            else:
                failed += 1

    print(f"\n{'─' * 40}")
    total = passed + failed
    if failed == 0:
        print(f"{GREEN}{BOLD}All {total} tests passed.{RESET}")
    else:
        print(f"{RED}{BOLD}{failed}/{total} tests failed.{RESET}")

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    main()
