"""DB-backed anti-flap persistence tests."""

import fleetent.runtime.context as _cm
from fleetent.runtime.context import (
    AntiFlapState,
    apply_anti_flap,
    load_anti_flap_state,
    save_anti_flap_state,
)

_BIG = {
    "max_tokens": 10_000,
    "tmax_ratio": 0.5,
    "tretained_ratio": 0.3,
    "keep_recent": 4,
}
_FLAP_CFG = {**_BIG, "flap_window": 3, "min_savings_ratio": 0.10, "min_interval_turns": 1}


def _big_msgs():
    return [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(100)
        ],
    ]


def test_anti_flap_persistence_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(_cm, "DB_PATH", tmp_path / "users.db")
    st = AntiFlapState(recent_savings=(0.05, 0.2), turns_since_last_compress=3, auto_disabled=True)
    save_anti_flap_state("sess-rt", st)
    loaded = load_anti_flap_state("sess-rt")
    assert loaded.recent_savings == (0.05, 0.2)
    assert loaded.turns_since_last_compress == 3
    assert loaded.auto_disabled is True


def test_anti_flap_load_absent_returns_default(tmp_path, monkeypatch):
    monkeypatch.setattr(_cm, "DB_PATH", tmp_path / "users.db")
    assert load_anti_flap_state("never-seen") == AntiFlapState()


def test_cross_run_accumulation_circuit_breaks(tmp_path, monkeypatch):
    # Simulate 3 separate runs (3 user messages): each run loads state from
    # users.db, does one low-savings auto compress, saves back. The savings window
    # must accumulate ACROSS runs (not reset per run) and trip the breaker on #3.
    monkeypatch.setattr(_cm, "DB_PATH", tmp_path / "users.db")
    monkeypatch.setattr(_cm, "_summarize", lambda m, prev_summary=None, config=None: "x" * 200000)
    sid = "sess-cross"
    cfg = {**_FLAP_CFG, "min_interval_turns": 1}
    for _ in range(3):
        st = load_anti_flap_state(sid)  # run boundary: load
        # advanced=turns+1 >= min_interval(1) -> compress this run
        _, st = apply_anti_flap(_big_msgs(), st, config=cfg)
        save_anti_flap_state(sid, st)  # run boundary: save
    final = load_anti_flap_state(sid)
    assert len(final.recent_savings) == 3
    assert final.auto_disabled is True  # 3 consecutive low-savings across runs
