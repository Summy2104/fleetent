"""Integration: schedule_store rejects the generate-task send-instruction footgun.

schedule-create-delivery-guardrail: a `generate` task with no explicit `deliver` whose
`message` embeds a send/delivery imperative ("把结果私信发送给 X") is the recurring footgun
(deliver falls back to the creation channel + the model self-delivers → mis-routed/duplicate).
`create` rejects it with corrective guidance. Configured-delivery / clean-message / action
tasks pass.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fleetent.db import SQLiteDatabase
from fleetent.schema_migrations import migrate


def _db(tmp_path: Path) -> SQLiteDatabase:
    from fleetent.runtime.agent_state_migrations import MIGRATIONS

    db = SQLiteDatabase(path=tmp_path / "agent_state.db")
    migrate(db, MIGRATIONS)
    return db


@pytest.fixture
def _ss(tmp_path):
    import fleetent.schedule_store as ss

    original = ss._state_db
    ss.set_state_db(_db(tmp_path))
    yield ss
    ss._state_db = original


def test_generate_no_deliver_with_send_instruction_rejected(_ss):
    with pytest.raises(ValueError, match="notify_target|action"):
        _ss.create(
            name="gold",
            cron_expr="*/30 * * * *",
            user_id="u1",
            message="查询金价并把结果以私信形式发送给 U094B755UQ3（程鑫）",
            task_type="generate",
        )


def test_generate_with_explicit_deliver_passes(_ss):
    task = _ss.create(
        name="gold",
        cron_expr="*/30 * * * *",
        user_id="u1",
        message="查询金价并把结果私信发送给 U1",  # mentions sending, but delivery is configured
        task_type="generate",
        deliver={"mode": "explicit", "platform": "slack", "target": "U1", "target_type": "user"},
    )
    assert task["id"]


def test_generate_clean_message_passes(_ss):
    task = _ss.create(
        name="gold",
        cron_expr="*/30 * * * *",
        user_id="u1",
        message="查询当前黄金现货价并输出正文：金价、涨跌幅、更新时间",
        task_type="generate",
    )
    assert task["id"]


def test_action_with_send_instruction_passes(_ss):
    task = _ss.create(
        name="gold",
        cron_expr="*/30 * * * *",
        user_id="u1",
        message="查询金价并用 send_im_message 私信发送给 U1",
        task_type="action",
    )
    assert task["id"]
