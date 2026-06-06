"""Unit tests: compaction checkpoint injection in runtime/context.py."""

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


def test_maybe_compress_calls_write_checkpoint_before_compress(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with (
        patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write,
        patch("fleetent.platform.chat_management.session_admin_store.update_compaction_meta"),
    ):
        result = cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id="sess-x")

    assert result is not _big_messages()  # compression happened
    mock_write.assert_called_once()
    call_args = mock_write.call_args
    assert call_args[0][0] == "sess-x"  # session_id correct
    assert isinstance(call_args[0][1], list)  # messages passed


def test_maybe_compress_calls_update_meta_after_compress(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with (
        patch("fleetent.session.manager.write_compaction_checkpoint"),
        patch(
            "fleetent.platform.chat_management.session_admin_store.update_compaction_meta"
        ) as mock_meta,
    ):
        cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id="sess-y")

    mock_meta.assert_called_once()
    kw = mock_meta.call_args.kwargs if mock_meta.call_args.kwargs else {}
    args = mock_meta.call_args.args
    assert "sess-y" in (args[0] if args else kw.get("session_id", ""))


def test_maybe_compress_no_checkpoint_when_no_session_id(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with (
        patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write,
        patch(
            "fleetent.platform.chat_management.session_admin_store.update_compaction_meta"
        ) as mock_meta,
    ):
        cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id=None)

    mock_write.assert_not_called()
    mock_meta.assert_not_called()


def test_maybe_compress_no_checkpoint_when_below_threshold(monkeypatch):
    import fleetent.runtime.context as cm

    with (
        patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write,
        patch(
            "fleetent.platform.chat_management.session_admin_store.update_compaction_meta"
        ) as mock_meta,
    ):
        # Very short messages — below threshold
        cm.maybe_compress(
            [{"role": "user", "content": "hi"}],
            config=_COMPRESS_CONFIG,
            session_id="sess-z",
        )

    mock_write.assert_not_called()
    mock_meta.assert_not_called()


def test_maybe_compress_checkpoint_write_failure_does_not_break_compress(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Summary text.")

    with (
        patch(
            "fleetent.session.manager.write_compaction_checkpoint",
            side_effect=OSError("disk full"),
        ),
        patch("fleetent.platform.chat_management.session_admin_store.update_compaction_meta"),
    ):
        result = cm.maybe_compress(_big_messages(), config=_COMPRESS_CONFIG, session_id="sess-fail")

    # Compression still happened despite checkpoint write failure
    assert result is not _big_messages()
    assert len(result) < len(_big_messages())


# ── compress_for_context_overflow ─────────────────────────────────────────────


def test_compress_for_context_overflow_calls_checkpoint(monkeypatch):
    import fleetent.runtime.context as cm

    monkeypatch.setattr(cm, "_summarize", lambda msgs, **kw: "Overflow summary.")

    with (
        patch("fleetent.session.manager.write_compaction_checkpoint") as mock_write,
        patch(
            "fleetent.platform.chat_management.session_admin_store.update_compaction_meta"
        ) as mock_meta,
    ):
        cm.compress_for_context_overflow(
            _big_messages(), config=_COMPRESS_CONFIG, session_id="sess-ov"
        )

    mock_write.assert_called_once()
    mock_meta.assert_called_once()
    assert mock_write.call_args[0][0] == "sess-ov"
