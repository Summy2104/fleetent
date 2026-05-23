import httpx
import pytest
import respx

from mini_agent.sandbox_client import SandboxClient


@pytest.fixture
def client():
    return SandboxClient(base_url="http://sandbox-test:7777")


@respx.mock
@pytest.mark.asyncio
async def test_create_workspace(client):
    respx.post("http://sandbox-test:7777/workspace").mock(
        return_value=httpx.Response(200, json={"id": "ws-abc"})
    )
    ws_id = await client.create_workspace("session-1")
    assert ws_id == "ws-abc"


@respx.mock
@pytest.mark.asyncio
async def test_exec_returns_result(client):
    respx.post("http://sandbox-test:7777/workspace/ws-abc/exec").mock(
        return_value=httpx.Response(200, json={"stdout": "hello", "stderr": "", "exit_code": 0})
    )
    result = await client.exec("ws-abc", "echo hello")
    assert result.stdout == "hello"
    assert result.exit_code == 0


@respx.mock
@pytest.mark.asyncio
async def test_exec_non_zero_exit_does_not_raise(client):
    respx.post("http://sandbox-test:7777/workspace/ws-abc/exec").mock(
        return_value=httpx.Response(200, json={"stdout": "", "stderr": "error", "exit_code": 1})
    )
    result = await client.exec("ws-abc", "false")
    assert result.exit_code == 1
    assert result.stderr == "error"


@respx.mock
@pytest.mark.asyncio
async def test_destroy_workspace(client):
    respx.delete("http://sandbox-test:7777/workspace/ws-abc").mock(
        return_value=httpx.Response(200, json={})
    )
    await client.destroy_workspace("ws-abc")  # should not raise
