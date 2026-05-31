import asyncio
import os

import pytest
import structlog

import fleetent.session_mgr as session_mgr
from fleetent.config import Settings


@pytest.fixture(autouse=True)
def _isolate_structlog():
    # Other tests (test_config) call configure_logging(), leaving structlog in a
    # global state whose add_logger_name processor crashes on PrintLogger. Reset
    # to library defaults so cleanup_expired's log calls are exercised cleanly.
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


@pytest.fixture
def sessions_dir(tmp_path, monkeypatch):
    d = tmp_path / "sessions"
    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", d)
    return d


def _set_mtime(path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


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


# --- Config / _default_config ---


def test_settings_has_session_ttl_days_default():
    assert Settings.model_fields["session_ttl_days"].default == 30


def test_default_config_returns_ttl_seconds(monkeypatch):
    monkeypatch.setattr(
        session_mgr,
        "_default_config",
        session_mgr._default_config,
    )
    # Avoid instantiating real Settings (anthropic_api_key required): patch loader.
    monkeypatch.setattr(
        "fleetent.config.Settings",
        lambda: type("S", (), {"session_ttl_days": 30})(),
    )
    cfg = session_mgr._default_config()
    assert cfg["ttl_seconds"] == 30 * 86400


# --- is_expired pure function ---


def test_is_expired_true_when_older_than_ttl():
    assert session_mgr.is_expired(mtime=0.0, now=101.0, ttl_seconds=100.0) is True


def test_is_expired_false_when_within_ttl():
    assert session_mgr.is_expired(mtime=50.0, now=100.0, ttl_seconds=100.0) is False


def test_is_expired_boundary_equal_not_expired():
    assert session_mgr.is_expired(mtime=0.0, now=100.0, ttl_seconds=100.0) is False


# --- cleanup_expired: basic delete ---


async def test_cleanup_deletes_expired_keeps_fresh(sessions_dir):
    await session_mgr.save("old", [{"role": "user", "content": "x"}])
    await session_mgr.save("fresh", [{"role": "user", "content": "y"}])
    now = 1_000_000.0
    ttl = 100.0
    _set_mtime(sessions_dir / "old.json", now - ttl - 10)
    _set_mtime(sessions_dir / "fresh.json", now - 1)

    removed = session_mgr.cleanup_expired(ttl_seconds=ttl, _now=now)

    assert removed == ["old"]
    assert not (sessions_dir / "old.json").exists()
    assert (sessions_dir / "fresh.json").exists()


async def test_cleanup_empty_dir_returns_empty(sessions_dir):
    removed = session_mgr.cleanup_expired(ttl_seconds=100.0, _now=1000.0)
    assert removed == []


# --- cleanup_expired: skip tmp + slash session_id ---


async def test_cleanup_skips_json_tmp(sessions_dir):
    sessions_dir.mkdir(parents=True, exist_ok=True)
    tmp = sessions_dir / "writing.json.tmp"
    tmp.write_text("[]")
    now = 1_000_000.0
    _set_mtime(tmp, now - 99999)

    removed = session_mgr.cleanup_expired(ttl_seconds=100.0, _now=now)

    assert removed == []
    assert tmp.exists()


async def test_cleanup_slash_session_id_restored(sessions_dir):
    sid = "u123/dm:U08XYZ"
    path = sessions_dir / f"{sid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]")
    now = 1_000_000.0
    ttl = 100.0
    _set_mtime(path, now - ttl - 10)

    removed = session_mgr.cleanup_expired(ttl_seconds=ttl, _now=now)

    assert removed == [sid]
    assert not (sessions_dir / f"{sid}.json").exists()


# --- cleanup_expired: delete fault tolerance ---


async def test_cleanup_unlink_failure_does_not_abort_batch(sessions_dir, monkeypatch):
    await session_mgr.save("bad", [{"role": "user", "content": "x"}])
    await session_mgr.save("good", [{"role": "user", "content": "y"}])
    now = 1_000_000.0
    ttl = 100.0
    _set_mtime(sessions_dir / "bad.json", now - ttl - 10)
    _set_mtime(sessions_dir / "good.json", now - ttl - 10)

    real_unlink = session_mgr.Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name == "bad.json":
            raise OSError("boom")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(session_mgr.Path, "unlink", flaky_unlink)

    removed = session_mgr.cleanup_expired(ttl_seconds=ttl, _now=now)

    assert removed == ["good"]
    assert (sessions_dir / "bad.json").exists()
    assert not (sessions_dir / "good.json").exists()


# --- cleanup_expired: TTL override integration ---


async def test_cleanup_falls_back_to_default_config(sessions_dir, monkeypatch):
    monkeypatch.setattr(
        session_mgr,
        "_default_config",
        lambda: {"ttl_seconds": 100.0},
    )
    await session_mgr.save("old", [{"role": "user", "content": "x"}])
    now = 1_000_000.0
    _set_mtime(sessions_dir / "old.json", now - 200)

    removed = session_mgr.cleanup_expired(_now=now)

    assert removed == ["old"]


async def test_cleanup_param_overrides_default_config(sessions_dir, monkeypatch):
    monkeypatch.setattr(
        session_mgr,
        "_default_config",
        lambda: {"ttl_seconds": 100.0},
    )
    await session_mgr.save("old", [{"role": "user", "content": "x"}])
    now = 1_000_000.0
    _set_mtime(sessions_dir / "old.json", now - 200)

    # Larger TTL via param means not expired, overriding default config.
    removed = session_mgr.cleanup_expired(ttl_seconds=10_000.0, _now=now)

    assert removed == []
    assert (sessions_dir / "old.json").exists()
