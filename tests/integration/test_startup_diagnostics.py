import json
from io import StringIO

from fleetent import structured_logging as sl
from fleetent.observability.startup_diagnostics import diagnose_database_writable


class FailingDatabase:
    def execute(self, sql: str):
        raise OSError("permission denied")


def test_database_unwritable_diagnostic_logs_component_reason_and_suggestion(
    monkeypatch,
    tmp_path,
):
    sl.configure_structured_logging(
        console_level="silent",
        file_level="debug",
        directory=tmp_path,
        console_stream=StringIO(),
    )
    monkeypatch.setattr(
        "fleetent.observability.startup_diagnostics.create_database",
        lambda database_url: FailingDatabase(),
    )

    assert diagnose_database_writable("sqlite:///blocked/fleetent.db") is False

    record = json.loads(next(tmp_path.glob("*.error.log")).read_text())
    assert record["level"] == "fatal"
    assert record["component"] == "database"
    assert record["fields"]["reason"] == "permission denied"
    assert "Check database directory permissions" in record["fields"]["suggestion"]
