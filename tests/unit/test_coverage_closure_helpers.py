from __future__ import annotations

import io
import json
from types import SimpleNamespace
from typing import Any

import pytest

from fleetent import structured_logging
from fleetent.config import VectorStoreSettings
from fleetent.observability import startup_diagnostics
from fleetent.platform import maintenance as platform_maintenance
from fleetent.vector_store import backend


def test_structured_logging_redacts_serializes_and_writes_outputs(tmp_path):
    stream = io.StringIO()
    structured_logging.configure_structured_logging(
        console_level="debug",
        file_level="warn",
        directory=tmp_path,
        console_stream=stream,
    )
    try:
        raise RuntimeError("failed for user@example.com with sk-secret123")
    except RuntimeError as exc:
        structured_logging.get_logger("component").warn(
            "Authorization: Bearer ma-" + "a" * 64,
            token="secret",
            token_estimate=42,
            nested={"api_key": "secret", "email": "user@example.com"},
            tuple_value=(object(), "13800138000"),
            exception=exc,
        )

    console = stream.getvalue()
    assert "[REDACTED:token]" in console
    assert "token_estimate=42" in console
    assert "[REDACTED:email]" in console
    assert "[REDACTED:phone]" in console
    log_lines = (
        (tmp_path / f"{structured_logging._today()}.log").read_text(encoding="utf-8").splitlines()
    )  # noqa: SLF001
    error_lines = (
        (
            tmp_path / f"{structured_logging._today()}.error.log"  # noqa: SLF001
        )
        .read_text(encoding="utf-8")
        .splitlines()
    )
    record = json.loads(log_lines[0])
    assert record["error_type"] == "RuntimeError"
    assert record["fields"]["serialization_fallback"] is True
    assert record["fields"]["token"] == "[REDACTED:token]"
    assert error_lines == log_lines
    assert structured_logging._is_enabled("error", "silent") is False  # noqa: SLF001


def test_startup_diagnostics_log_success_failure_and_provider_keys(monkeypatch):
    messages: list[tuple[str, str, dict[str, Any]]] = []

    class FakeLogger:
        def __init__(self, component: str) -> None:
            self.component = component

        def info(self, message: str, **fields: Any) -> None:
            messages.append((self.component, f"info:{message}", fields))

        def warn(self, message: str, **fields: Any) -> None:
            messages.append((self.component, f"warn:{message}", fields))

        def fatal(self, message: str, **fields: Any) -> None:
            messages.append((self.component, f"fatal:{message}", fields))

    monkeypatch.setattr(startup_diagnostics, "get_logger", lambda component: FakeLogger(component))
    startup_diagnostics.log_config_loaded()
    startup_diagnostics.log_config_failed(ValueError("bad config"))

    class GoodDb:
        def execute(self, sql: str) -> None:
            messages.append(("db", sql, {}))

    monkeypatch.setattr(startup_diagnostics, "create_database", lambda _url: GoodDb())
    assert startup_diagnostics.diagnose_database_writable("sqlite:///ok.db")

    class BadDb:
        def execute(self, sql: str) -> None:
            raise OSError("readonly")

    monkeypatch.setattr(startup_diagnostics, "create_database", lambda _url: BadDb())
    assert not startup_diagnostics.diagnose_database_writable("sqlite:///bad.db")
    monkeypatch.delenv("MISSING_KEY", raising=False)
    startup_diagnostics.diagnose_provider_keys(
        [
            SimpleNamespace(api_key_env="MISSING_KEY"),
            SimpleNamespace(api_key_env="MISSING_KEY"),
        ]
    )
    startup_diagnostics.log_mcp_server_unreachable("mcp1", "timeout")
    assert ("config", "info:config loaded", {}) in messages
    assert any(
        component == "database" and message.startswith("fatal:")
        for component, message, _ in messages
    )
    assert (
        sum(
            1
            for _component, message, _fields in messages
            if message == "warn:provider api key missing"
        )
        == 1
    )
    assert any(fields.get("server_id") == "mcp1" for _component, _message, fields in messages)


def test_platform_maintenance_summaries_and_confirmation(monkeypatch):
    recorded: list[Any] = []
    monkeypatch.setattr(platform_maintenance, "record_trace_event", recorded.append)
    monkeypatch.setattr(platform_maintenance.uuid, "uuid4", lambda: "fixed")

    with pytest.raises(platform_maintenance.ConfirmationRequired, match="requires --yes"):
        platform_maintenance.require_confirmation(yes=False, dry_run_command="fleetent dry-run")
    platform_maintenance.require_confirmation(yes=True, dry_run_command="ignored")

    dry = platform_maintenance.compact_memory(dry_run=True, actor="admin")
    assert dry.to_dict() == {
        "affected_counts": {"memories_compacted": 0},
        "audit_ref": None,
        "command": "memory compact",
        "dry_run": True,
        "skipped_reasons": [],
    }
    assert (
        platform_maintenance.compact_memory(dry_run=False, actor="admin").audit_ref == "trace:fixed"
    )
    assert platform_maintenance.run_kb_sync(
        connector_id="gdrive", dry_run=False, actor="admin"
    ).affected_counts == {"connectors": 1}
    assert platform_maintenance.reindex_vector(
        namespace="memory", dry_run=False, actor="admin"
    ).affected_counts == {"namespaces": 1}
    assert platform_maintenance.run_reflection(
        scope="tenant", dry_run=False, actor="admin"
    ).affected_counts == {"scopes": 1}
    assert recorded[-1].payload == {
        "actor": "admin",
        "command": "reflection run",
        "scope": "tenant",
    }


async def test_vector_backend_memory_backend_and_pure_helpers(tmp_path):
    memory_backend = backend.create_vector_backend(VectorStoreSettings(backend="memory"))
    await memory_backend.upsert("b", [0.0, 1.0], "ns")
    await memory_backend.upsert("a", [1.0, 0.0], "ns")
    assert [result.id for result in await memory_backend.search([1.0, 0.0], "ns", limit=2)] == [
        "a",
        "b",
    ]
    assert await memory_backend.search([1.0], "ns", limit=0) == []
    await memory_backend.delete("a", "ns")
    assert [result.id for result in await memory_backend.search([1.0, 0.0], "ns")] == ["b"]
    await memory_backend.clear_namespace("ns")
    assert await memory_backend.search([1.0, 0.0], "ns") == []

    assert backend._similarity([1.0], [1.0, 2.0]) == 0.0  # noqa: SLF001
    assert backend._similarity([0.0], [1.0]) == 0.0  # noqa: SLF001
    assert backend._similarity([2.0], [2.0]) == 1.0  # noqa: SLF001
    assert backend._load_vector("[1, 2.5]") == [1.0, 2.5]  # noqa: SLF001
    assert backend._load_vector("not-json") is None  # noqa: SLF001
    assert backend._load_vector("{}") is None  # noqa: SLF001
    assert backend._load_vector("[true]") is None  # noqa: SLF001
    assert backend._sqlite_path("sqlite:///relative.db").as_posix() == "relative.db"  # noqa: SLF001
    assert backend._sqlite_path("sqlite:////tmp/vector.db").as_posix() == "/tmp/vector.db"  # noqa: SLF001
    backend.SQLiteVectorBackend(f"sqlite:///{tmp_path / 'vectors.db'}")
    with pytest.raises(ValueError, match="local sqlite"):
        backend.SQLiteVectorBackend("postgresql://db")
    with pytest.raises(ValueError, match="requires a local sqlite"):
        backend.create_vector_backend(VectorStoreSettings(backend="sqlite"))
    with pytest.raises(ValueError, match="Unsupported"):
        backend.create_vector_backend(VectorStoreSettings(backend="unknown"))  # type: ignore[arg-type]
