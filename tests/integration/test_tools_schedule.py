"""Tests for schedule_task and cancel_task tools."""

from unittest.mock import patch


def test_schedule_task_returns_success_with_task_id():
    import fleetent.schedule_store as ss
    import fleetent.tools  # noqa: F401 — register tools

    fake_task = {"id": "uuid-123", "name": "daily"}

    with patch.object(ss, "create", return_value=fake_task) as mock_create:
        from fleetent.tools.registry import dispatch

        payload = (
            '{"name":"daily","cron_expr":"0 9 * * *","message":"run",'
            '"timezone":"UTC","user_id":"u-1"}'
        )
        result = dispatch(
            "schedule_task",
            payload,
        )

    mock_create.assert_called_once()
    assert "uuid-123" in result


def test_cancel_task_returns_success_when_found():
    import fleetent.schedule_store as ss
    import fleetent.tools  # noqa: F401

    with patch.object(ss, "delete", return_value=True):
        from fleetent.tools.registry import dispatch

        result = dispatch("cancel_task", '{"task_id":"uuid-123"}')

    assert "uuid-123" in result
    assert "cancel" in result.lower() or "delet" in result.lower() or "remov" in result.lower()


def test_cancel_task_returns_error_when_not_found():
    import fleetent.schedule_store as ss
    import fleetent.tools  # noqa: F401

    with patch.object(ss, "delete", return_value=False):
        from fleetent.tools.registry import dispatch

        result = dispatch("cancel_task", '{"task_id":"no-such-id"}')

    assert "no-such-id" in result
    assert "not found" in result.lower() or "error" in result.lower()
