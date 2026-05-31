import asyncio
import os

import pytest
import structlog

import fleetent.session_index as session_index
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


@pytest.fixture(autouse=True)
def index_db(tmp_path, monkeypatch):
    # Isolate the metadata index DB for every test: save() now writes to it as a
    # side effect, and tests must never touch the real data/users.db.
    monkeypatch.setattr(session_index, "DB_PATH", tmp_path / "x.db")
    return tmp_path / "x.db"


def _set_mtime(path, mtime: float) -> None:
    os.utime(path, (mtime, mtime))


# --- 7. save() records metadata after successful atomic write ---


async def test_save_records_metadata(sessions_dir, index_db):
    messages = [{"role": "user", "content": "a"}, {"role": "assistant", "content": "b"}]
    await session_mgr.save("sess-1", messages, user_id="u1", agent_name="bot")
    meta = session_index.get("sess-1")
    assert meta is not None
    assert meta["message_count"] == 2
    assert meta["user_id"] == "u1"
    assert meta["agent_name"] == "bot"


async def test_save_backward_compatible_two_args(sessions_dir, index_db):
    """Existing two-arg callers still work; metadata gets NULL user/agent."""
    await session_mgr.save("sess-1", [{"role": "user", "content": "x"}])
    assert (await session_mgr.load("sess-1")) == [{"role": "user", "content": "x"}]
    meta = session_index.get("sess-1")
    assert meta is not None
    assert meta["message_count"] == 1
    assert meta["user_id"] is None
    assert meta["agent_name"] is None


# --- 8. index failure must not break message persistence ---


async def test_save_index_failure_does_not_break_message_write(sessions_dir, index_db, monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("index down")

    monkeypatch.setattr(session_index, "record_activity", boom)

    messages = [{"role": "user", "content": "x"}]
    # Must not raise despite the index failure.
    await session_mgr.save("sess-1", messages)

    # Message file is intact.
    assert (await session_mgr.load("sess-1")) == messages
    # Index has no row (write failed and was swallowed).
    assert session_index.get("sess-1") is None


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
    # _default_config() now also reads the capacity fields, so the stub must
    # provide them too.
    monkeypatch.setattr(
        "fleetent.config.Settings",
        lambda: type(
            "S",
            (),
            {"session_ttl_days": 30, "session_max_total_mb": 1024, "session_max_count": 10000},
        )(),
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


# --- Capacity config: Settings fields + _default_config ---


def test_settings_has_session_max_total_mb_default():
    assert Settings.model_fields["session_max_total_mb"].default == 1024


def test_settings_has_session_max_count_default():
    assert Settings.model_fields["session_max_count"].default == 10000


def test_default_config_returns_capacity_limits(monkeypatch):
    # Avoid instantiating real Settings (anthropic_api_key required): patch loader.
    monkeypatch.setattr(
        "fleetent.config.Settings",
        lambda: type(
            "S",
            (),
            {"session_ttl_days": 30, "session_max_total_mb": 2, "session_max_count": 5},
        )(),
    )
    cfg = session_mgr._default_config()
    assert cfg["max_total_bytes"] == 2 * 1024 * 1024
    assert cfg["max_count"] == 5
    # TTL still present (extends, not replaces).
    assert cfg["ttl_seconds"] == 30 * 86400


# --- is_over_capacity pure function ---


def test_is_over_capacity_size_over():
    assert session_mgr.is_over_capacity(101, 1, max_total_bytes=100, max_count=10) is True


def test_is_over_capacity_count_over():
    assert session_mgr.is_over_capacity(10, 11, max_total_bytes=100, max_count=10) is True


def test_is_over_capacity_neither_over():
    assert session_mgr.is_over_capacity(50, 5, max_total_bytes=100, max_count=10) is False


def test_is_over_capacity_size_dimension_disabled():
    # max_total_bytes=0 disables the size dimension; huge total does not trigger.
    assert session_mgr.is_over_capacity(10_000, 5, max_total_bytes=0, max_count=10) is False


def test_is_over_capacity_count_dimension_disabled():
    assert session_mgr.is_over_capacity(50, 10_000, max_total_bytes=100, max_count=0) is False


def test_is_over_capacity_both_disabled():
    assert session_mgr.is_over_capacity(10_000, 10_000, max_total_bytes=0, max_count=0) is False


# --- enforce_capacity: size dimension LRU eviction ---


async def test_enforce_capacity_evicts_oldest_until_size_under_limit(sessions_dir):
    # Three sessions of ~equal size; oldest must go first.
    for sid, mtime in (("old", 100.0), ("mid", 200.0), ("new", 300.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x" * 50}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    sizes = {p.name: p.stat().st_size for p in sessions_dir.glob("*.json")}
    total = sum(sizes.values())
    # Limit allows only two files: must drop exactly the oldest one.
    limit = total - 1

    removed = session_mgr.enforce_capacity(max_total_bytes=limit, max_count=0)

    assert removed == ["old"]
    assert not (sessions_dir / "old.json").exists()
    assert (sessions_dir / "mid.json").exists()
    assert (sessions_dir / "new.json").exists()


async def test_enforce_capacity_no_eviction_when_under_size_limit(sessions_dir):
    await session_mgr.save("a", [{"role": "user", "content": "x"}])
    _set_mtime(sessions_dir / "a.json", 100.0)

    removed = session_mgr.enforce_capacity(max_total_bytes=10_000_000, max_count=0)

    assert removed == []
    assert (sessions_dir / "a.json").exists()


async def test_enforce_capacity_empty_dir_returns_empty(sessions_dir):
    removed = session_mgr.enforce_capacity(max_total_bytes=100, max_count=100)
    assert removed == []


async def test_enforce_capacity_does_not_over_evict(sessions_dir):
    # Two small + one large; dropping just the oldest large should suffice.
    await session_mgr.save("big_old", [{"role": "user", "content": "x" * 500}])
    await session_mgr.save("small_mid", [{"role": "user", "content": "y"}])
    await session_mgr.save("small_new", [{"role": "user", "content": "z"}])
    _set_mtime(sessions_dir / "big_old.json", 100.0)
    _set_mtime(sessions_dir / "small_mid.json", 200.0)
    _set_mtime(sessions_dir / "small_new.json", 300.0)

    sizes = {p.name: p.stat().st_size for p in sessions_dir.glob("*.json")}
    # Limit fits the two small ones but not the big one.
    limit = sizes["small_mid.json"] + sizes["small_new.json"]

    removed = session_mgr.enforce_capacity(max_total_bytes=limit, max_count=0)

    assert removed == ["big_old"]
    assert (sessions_dir / "small_mid.json").exists()
    assert (sessions_dir / "small_new.json").exists()


# --- enforce_capacity: count dimension + dimension disabling ---


async def test_enforce_capacity_evicts_oldest_until_count_under_limit(sessions_dir):
    for sid, mtime in (("a", 100.0), ("b", 200.0), ("c", 300.0), ("d", 400.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x"}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=2)

    # 4 files, max 2 -> drop the two oldest (a, b) in order.
    assert removed == ["a", "b"]
    assert not (sessions_dir / "a.json").exists()
    assert not (sessions_dir / "b.json").exists()
    assert (sessions_dir / "c.json").exists()
    assert (sessions_dir / "d.json").exists()


async def test_enforce_capacity_both_dimensions_disabled_evicts_nothing(sessions_dir):
    for sid in ("a", "b", "c"):
        await session_mgr.save(sid, [{"role": "user", "content": "x" * 100}])

    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=0)

    assert removed == []
    assert len(list(sessions_dir.glob("*.json"))) == 3


async def test_enforce_capacity_disabled_dimension_not_a_stop_condition(sessions_dir):
    # Count is over (3 > 2) but size dimension is disabled; eviction driven by count.
    for sid, mtime in (("a", 100.0), ("b", 200.0), ("c", 300.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x"}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=2)

    assert removed == ["a"]


async def test_enforce_capacity_evicts_until_both_constraints_satisfied(sessions_dir):
    # Size limit alone would drop 1; count limit forces dropping more.
    for sid, mtime in (("a", 100.0), ("b", 200.0), ("c", 300.0), ("d", 400.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x"}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    sizes = {p.name: p.stat().st_size for p in sessions_dir.glob("*.json")}
    total = sum(sizes.values())
    # Size limit only needs one dropped, but count=1 forces dropping three.
    removed = session_mgr.enforce_capacity(max_total_bytes=total - 1, max_count=1)

    assert removed == ["a", "b", "c"]
    assert (sessions_dir / "d.json").exists()


# --- enforce_capacity: fall back to _default_config ---


async def test_enforce_capacity_falls_back_to_default_config(sessions_dir, monkeypatch):
    monkeypatch.setattr(
        session_mgr,
        "_default_config",
        lambda: {"ttl_seconds": 100.0, "max_total_bytes": 0.0, "max_count": 2.0},
    )
    for sid, mtime in (("a", 100.0), ("b", 200.0), ("c", 300.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x"}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    removed = session_mgr.enforce_capacity()

    assert removed == ["a"]


# --- enforce_capacity: skip tmp + slash session_id restore ---


async def test_enforce_capacity_skips_json_tmp(sessions_dir):
    sessions_dir.mkdir(parents=True, exist_ok=True)
    tmp = sessions_dir / "writing.json.tmp"
    tmp.write_text("[]")
    _set_mtime(tmp, 1.0)
    await session_mgr.save("a", [{"role": "user", "content": "x"}])
    _set_mtime(sessions_dir / "a.json", 100.0)

    # Force eviction by count; tmp must not be counted or deleted.
    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=0)

    assert tmp.exists()
    assert removed == []


async def test_enforce_capacity_slash_session_id_restored(sessions_dir):
    sid = "u123/dm:U08XYZ"
    path = sessions_dir / f"{sid}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("[]")
    _set_mtime(path, 100.0)
    await session_mgr.save("newer", [{"role": "user", "content": "x"}])
    _set_mtime(sessions_dir / "newer.json", 300.0)

    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=1)

    assert removed == [sid]
    assert not (sessions_dir / f"{sid}.json").exists()
    assert (sessions_dir / "newer.json").exists()


# --- enforce_capacity: delete fault tolerance ---


async def test_enforce_capacity_unlink_failure_does_not_abort_batch(sessions_dir, monkeypatch):
    # bad is oldest (tried first and fails); good is next-oldest and must still be deleted.
    for sid, mtime in (("bad", 100.0), ("good", 200.0), ("keep", 300.0)):
        await session_mgr.save(sid, [{"role": "user", "content": "x"}])
        _set_mtime(sessions_dir / f"{sid}.json", mtime)

    real_unlink = session_mgr.Path.unlink

    def flaky_unlink(self, *args, **kwargs):
        if self.name == "bad.json":
            raise OSError("boom")
        return real_unlink(self, *args, **kwargs)

    monkeypatch.setattr(session_mgr.Path, "unlink", flaky_unlink)

    # Limit allows two files -> exactly one eviction is attempted (the oldest, bad).
    # bad's unlink fails but the batch must not abort or over-evict healthy sessions;
    # the accumulator is decremented per eviction attempt so a stuck file does not
    # cascade into deleting good/keep.
    removed = session_mgr.enforce_capacity(max_total_bytes=0, max_count=2)

    assert removed == []  # bad's deletion failed, so it is not reported as removed
    assert (sessions_dir / "bad.json").exists()
    assert (sessions_dir / "good.json").exists()
    assert (sessions_dir / "keep.json").exists()
