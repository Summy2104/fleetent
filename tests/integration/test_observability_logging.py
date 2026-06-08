import json
from io import StringIO

from fleetent import structured_logging as sl
from fleetent.observability import get_logger


def test_get_logger_returns_component_logger_with_standard_levels():
    logger = get_logger("server")

    assert logger.component == "server"
    for level in ("fatal", "error", "warn", "info", "debug", "trace"):
        assert callable(getattr(logger, level))


def test_console_and_file_levels_are_filtered_independently(tmp_path):
    console = StringIO()
    sl.configure_structured_logging(
        console_level="info",
        file_level="debug",
        directory=tmp_path,
        console_stream=console,
    )

    logger = get_logger("server")
    logger.info("server started", port=8000)
    logger.debug("route selected", route="default")

    assert "server started" in console.getvalue()
    assert "route selected" not in console.getvalue()

    records = [json.loads(line) for line in next(tmp_path.glob("*.log")).read_text().splitlines()]
    assert [record["message"] for record in records] == ["server started", "route selected"]


def test_silent_channel_disables_output(tmp_path):
    console = StringIO()
    sl.configure_structured_logging(
        console_level="silent",
        file_level="silent",
        directory=tmp_path,
        console_stream=console,
    )

    get_logger("server").fatal("server failed")

    assert console.getvalue() == ""
    assert list(tmp_path.iterdir()) == []


def test_file_logging_creates_directory_and_splits_error_records(tmp_path):
    log_dir = tmp_path / "nested" / "logs"
    sl.configure_structured_logging(
        console_level="silent",
        file_level="trace",
        directory=log_dir,
        console_stream=StringIO(),
    )

    logger = get_logger("worker")
    logger.info("job queued", job_id="job-1")
    logger.warn("job delayed", job_id="job-1")
    logger.error("job failed", job_id="job-1")

    full_log = next(path for path in log_dir.glob("*.log") if not path.name.endswith(".error.log"))
    error_log = next(log_dir.glob("*.error.log"))
    full_records = [json.loads(line) for line in full_log.read_text().splitlines()]
    error_records = [json.loads(line) for line in error_log.read_text().splitlines()]

    assert [record["message"] for record in full_records] == [
        "job queued",
        "job delayed",
        "job failed",
    ]
    assert [record["message"] for record in error_records] == ["job delayed", "job failed"]


def test_log_output_redacts_tokens_credentials_and_contacts(tmp_path):
    console = StringIO()
    sl.configure_structured_logging(
        console_level="debug",
        file_level="debug",
        directory=tmp_path,
        console_stream=console,
    )

    get_logger("auth").info(
        "Authorization: Bearer sk-test-secret email alice@example.com phone 13800138000",
        password="plain-password",
        nested={"api_key": "ma-" + "a" * 64, "note": "contact bob@example.com"},
        token="xoxb-sensitive-token",
    )

    full_log = next(tmp_path.glob("*.log"))
    output = console.getvalue() + full_log.read_text()

    assert "sk-test-secret" not in output
    assert "alice@example.com" not in output
    assert "13800138000" not in output
    assert "plain-password" not in output
    assert "xoxb-sensitive-token" not in output
    assert "ma-" + "a" * 64 not in output
    assert "[REDACTED:token]" in output
    assert "[REDACTED:email]" in output
    assert "[REDACTED:phone]" in output


def test_exception_log_persists_error_details(tmp_path):
    sl.configure_structured_logging(
        console_level="silent",
        file_level="debug",
        directory=tmp_path,
        console_stream=StringIO(),
    )

    try:
        raise RuntimeError("database unavailable")
    except RuntimeError as exc:
        get_logger("database").error("startup database check failed", exception=exc)

    record = json.loads(next(tmp_path.glob("*.log")).read_text())

    assert record["error_type"] == "RuntimeError"
    assert record["error_message"] == "database unavailable"
    assert "RuntimeError: database unavailable" in record["stack"]
    assert record["file"].endswith("test_observability_logging.py")
    assert isinstance(record["line"], int)


def test_file_output_failure_does_not_break_console(monkeypatch, tmp_path):
    console = StringIO()
    sl.configure_structured_logging(
        console_level="info",
        file_level="info",
        directory=tmp_path,
        console_stream=console,
    )

    def fail_file(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(sl, "_write_jsonl", fail_file)

    get_logger("server").info("server still starts")

    assert "server still starts" in console.getvalue()


def test_console_output_failure_does_not_break_file(monkeypatch, tmp_path):
    class BrokenConsole(StringIO):
        def write(self, value: str) -> int:
            raise OSError("console closed")

    sl.configure_structured_logging(
        console_level="info",
        file_level="info",
        directory=tmp_path,
        console_stream=BrokenConsole(),
    )

    get_logger("server").info("server still writes file")

    record = json.loads(next(tmp_path.glob("*.log")).read_text())
    assert record["message"] == "server still writes file"


def test_file_json_serialization_falls_back_to_string(tmp_path):
    sl.configure_structured_logging(
        console_level="silent",
        file_level="info",
        directory=tmp_path,
        console_stream=StringIO(),
    )

    get_logger("serializer").info("record object", payload=object())

    record = json.loads(next(tmp_path.glob("*.log")).read_text())
    assert isinstance(record["fields"]["payload"], str)
    assert record["fields"]["serialization_fallback"] is True
