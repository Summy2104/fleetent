"""Unit tests: compaction checkpoint (pre-compact backup) injection in runtime/context.py.

Only the agent-side backup file (write_compaction_checkpoint) is exercised here;
session_meta stats recording was removed (Agent/Platform decoupling — compaction
stats live in observability traces).
"""

from __future__ import annotations

from unittest.mock import patch


def _big_messages(count: int = 100) -> list[dict]:
    return [
        {"role": "system", "content": "sys"},
        *[
            {"role": "user" if i % 2 == 0 else "assistant", "content": "x" * 2000}
            for i in range(count)
        ],
    ]


_COMPRESS_CONFIG = {
    "max_tokens": 10_000,
    "tmax_ratio": 0.5,
    "tretained_ratio": 0.3,
    "keep_recent": 4,
}


# ── maybe_compress ────────────────────────────────────────────────────────────


def test_maybe_compress_writes_checkpoint_before_compress(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write:
        result = cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id="sess-x")

    assert result is not _big_messages()  # compression happened
    mock_write.assert_called_once()
    assert mock_write.call_args[0][0] == "sess-x"
    assert isinstance(mock_write.call_args[0][1], list)


def test_maybe_compress_no_checkpoint_when_no_session_id(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write:
        cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id=None)

    mock_write.assert_not_called()


def test_maybe_compress_no_checkpoint_when_below_threshold(monkeypatch):
    import fleetent.runtime.context as cm

    with patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write:
        cm.maybe_compress(
            [{"role": "user", "content": "hi"}],
            config=_COMPRESS_CONFIG,
            session_id="sess-z",
        )

    mock_write.assert_not_called()


def test_maybe_compress_checkpoint_write_failure_does_not_break_compress(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with patch(
        "fleetent.session.manager.write_compaction_checkpoint",
        side_effect=OSError("disk full"),
    ):
        result = cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id="sess-fail")

    # Compression still happened despite checkpoint write failure (best-effort)
    assert result is not _big_messages()
    assert len(result) < len(_big_messages())


# ── compress_for_context_overflow ─────────────────────────────────────────────


def test_compress_for_context_overflow_writes_checkpoint(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Overflow summary.")

    with patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write:
        cm.compress_for_context_overflow(
            _big_messages(), config=_COMPRESS_CONFIG, session_id="sess-ov"
        )

    mock_write.assert_called_once()
    assert mock_write.call_args[0][0] == "sess-ov"
