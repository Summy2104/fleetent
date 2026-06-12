"""`schedule` tool carries task_type / notify_text and surfaces validation errors as text."""

from __future__ import annotations

from unittest.mock import patch

import fleetent.tools  # noqa: F401 — register tools
from fleetent.tools.registry import dispatch


async def test_schedule_create_notify_threads_type_and_text():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "n1"}) as mock_create:
        payload = (
            '{"action":"create","name":"晨会","cron_expr":"0 9 * * 1-5",'
            '"task_type":"notify","notify_text":"📅 9点开晨会",'
            '"notify_platform":"slack","notify_target":"C1","notify_target_type":"channel"}'
        )
        result = await dispatch("schedule", payload)

    kwargs = mock_create.call_args.kwargs
    assert kwargs["task_type"] == "notify"
    assert kwargs["notify_text"] == "📅 9点开晨会"
    assert "n1" in result


async def test_schedule_create_defaults_to_generate():
    import fleetent.schedule_store as ss

    with patch.object(ss, "create", return_value={"id": "g1"}) as mock_create:
        payload = '{"action":"create","name":"r","cron_expr":"0 9 * * *","message":"do"}'
        await dispatch("schedule", payload)

    assert mock_create.call_args.kwargs["task_type"] == "generate"


async def test_schedule_create_validation_error_is_text_not_raise():
    import fleetent.schedule_store as ss

    def _raise(**k):
        raise ValueError("notify task requires notify_text")

    with patch.object(ss, "create", _raise):
        result = await dispatch("schedule", '{"action":"create","name":"x","task_type":"notify"}')
    # The tool must return a clean error string, not propagate the exception.
    assert "notify_text" in result or "error" in result.lower()
