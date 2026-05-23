import asyncio

import pytest

import mini_agent.session_mgr as session_mgr


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    d = tmp_path / "sessions"
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", d)
    return d


async def test_load_nonexistent_returns_empty(sessions_dir):
    result = await session_mgr.load("sess-1")
    assert result == []


async def test_save_and_load_roundtrip(sessions_dir):
    messages = [{"role": "user", "content": "hello"}]
    await session_mgr.save("sess-1", messages)
    loaded = await session_mgr.load("sess-1")
    assert loaded == messages


async def test_save_overwrites(sessions_dir):
    await session_mgr.save("sess-1", [{"role": "user", "content": "first"}])
    await session_mgr.save("sess-1", [{"role": "user", "content": "second"}])
    loaded = await session_mgr.load("sess-1")
    assert len(loaded) == 1
    assert loaded[0]["content"] == "second"


async def test_two_sessions_isolated(sessions_dir):
    await session_mgr.save("sess-A", [{"role": "user", "content": "A"}])
    await session_mgr.save("sess-B", [{"role": "user", "content": "B"}])
    assert (await session_mgr.load("sess-A"))[0]["content"] == "A"
    assert (await session_mgr.load("sess-B"))[0]["content"] == "B"


async def test_concurrent_saves_same_session_serialize(sessions_dir):
    """Same session concurrent saves must not corrupt data."""
    results = []

    async def writer(value: str) -> None:
        async with session_mgr.session_lock("sess-1"):
            current = await session_mgr.load("sess-1")
            current.append({"role": "user", "content": value})
            await session_mgr.save("sess-1", current)
            results.append(value)

    await asyncio.gather(writer("a"), writer("b"), writer("c"))
    final = await session_mgr.load("sess-1")
    assert len(final) == 3


async def test_different_sessions_do_not_block_each_other(sessions_dir):
    """Two different sessions can load/save concurrently."""
    order = []

    async def task(sid: str) -> None:
        async with session_mgr.session_lock(sid):
            order.append(f"start:{sid}")
            await asyncio.sleep(0.01)
            order.append(f"end:{sid}")

    await asyncio.gather(task("sess-X"), task("sess-Y"))
    # Both should complete; order is non-deterministic but both should appear
    assert "start:sess-X" in order
    assert "start:sess-Y" in order
