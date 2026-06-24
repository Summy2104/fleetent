"""Structured program logging for fleetent components."""

from __future__ import annotations

import json
import re
import sys
import traceback
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TextIO

from fleetent import paths

_LEVELS = {
    "silent": 0,
    "fatal": 1,
    "error": 2,
    "warn": 3,
    "info": 4,
    "debug": 5,
    "trace": 6,
}


@dataclass
class _LoggingConfig:
    console_level: str = "info"
    file_level: str = "debug"
    directory: Path = field(default_factory=paths.logs_dir)
    console_stream: TextIO = sys.stdout


_config = _LoggingConfig()

_SENSITIVE_KEYS = ("password", "secret", "token", "api_key", "authorization")
_BEARER_RE = re.compile(r"Authorization:\s*Bearer\s+\S+", re.IGNORECASE)
_API_KEY_RE = re.compile(r"\b(?:sk-[A-Za-z0-9._-]+|ma-[0-9a-fA-F]{64})\b")
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_CN_PHONE_RE = re.compile(r"\b1[3-9]\d{9}\b")


@dataclass(frozen=True)
class Logger:
    """Component-scoped structured logger."""

    component: str

    def fatal(self, message: str, **fields: Any) -> None:
        self._log("fatal", message, fields)

    def error(self, message: str, **fields: Any) -> None:
        self._log("error", message, fields)

    def warn(self, message: str, **fields: Any) -> None:
        self._log("warn", message, fields)

    def info(self, message: str, **fields: Any) -> None:
        self._log("info", message, fields)

    def debug(self, message: str, **fields: Any) -> None:
        self._log("debug", message, fields)

    def trace(self, message: str, **fields: Any) -> None:
        self._log("trace", message, fields)

    def _log(self, level: str, message: str, fields: dict[str, Any]) -> None:
        record = _make_record(level, self.component, message, fields)
        if _is_enabled(level, _config.console_level):
            with suppress(Exception):
                _write_console(record)
        if _is_enabled(level, _config.file_level):
            date = _today()
            try:
                _write_jsonl(_config.directory / f"{date}.log", record)
                if level in {"fatal", "error", "warn"}:
                    _write_jsonl(_config.directory / f"{date}.error.log", record)
            except Exception:
                pass


def get_logger(component: str) -> Logger:
    """Return a structured logger for a component."""
    return Logger(component=component)


def configure_structured_logging(
    *,
    console_level: str = "info",
    file_level: str = "debug",
    directory: str | Path | None = None,
    console_stream: TextIO | None = None,
) -> None:
    """Configure structured logging outputs."""
    global _config
    resolved_dir = Path(directory) if directory else paths.logs_dir()
    _config = _LoggingConfig(
        console_level=console_level,
        file_level=file_level,
        directory=resolved_dir,
        console_stream=console_stream or sys.stdout,
    )


def _is_enabled(level: str, configured_level: str) -> bool:
    configured_value = _LEVELS[configured_level]
    return configured_value != 0 and _LEVELS[level] <= configured_value


def _make_record(
    level: str,
    component: str,
    message: str,
    fields: dict[str, Any],
) -> dict[str, Any]:
    clean_fields = dict(fields)
    exception = clean_fields.pop("exception", None)
    redacted_fields = _redact_value(clean_fields)
    json_fields, used_fallback = _json_safe_fields(redacted_fields)
    if used_fallback:
        json_fields["serialization_fallback"] = True
    record = {
        "ts": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "level": level,
        "component": component,
        "message": _redact_text(message),
        "fields": json_fields,
    }
    if isinstance(exception, BaseException):
        record.update(_exception_fields(exception))
    return record


def _write_console(record: dict[str, Any]) -> None:
    fields = " ".join(f"{key}={value}" for key, value in record["fields"].items())
    line = f"{record['ts']} {record['level']} {record['component']} {record['message']}"
    if fields:
        line = f"{line} {fields}"
    print(line, file=_config.console_stream)


def _write_jsonl(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _redact_value(value: Any, key: str | None = None) -> Any:
    normalized_key = key.lower() if key is not None else None
    if normalized_key == "token_estimate":
        return value
    if normalized_key is not None and _is_sensitive_key(normalized_key):
        return "[REDACTED:token]"
    if isinstance(value, str):
        return _redact_text(value)
    if isinstance(value, dict):
        return {
            str(item_key): _redact_value(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    return value


def _is_sensitive_key(normalized_key: str) -> bool:
    if normalized_key == "token":
        return True
    if normalized_key.endswith("_token") or normalized_key.endswith("-token"):
        return True
    return any(
        marker in normalized_key for marker in ("password", "secret", "api_key", "authorization")
    )


def _redact_text(value: str) -> str:
    redacted = _BEARER_RE.sub("Authorization: Bearer [REDACTED:token]", value)
    redacted = _API_KEY_RE.sub("[REDACTED:token]", redacted)
    redacted = _EMAIL_RE.sub("[REDACTED:email]", redacted)
    return _CN_PHONE_RE.sub("[REDACTED:phone]", redacted)


def _exception_fields(exception: BaseException) -> dict[str, Any]:
    tb = exception.__traceback__
    while tb is not None and tb.tb_next is not None:
        tb = tb.tb_next
    file_name = tb.tb_frame.f_code.co_filename if tb is not None else ""
    line = tb.tb_lineno if tb is not None else 0
    return {
        "error_type": type(exception).__name__,
        "error_message": _redact_text(str(exception)),
        "stack": "".join(
            traceback.format_exception(type(exception), exception, exception.__traceback__)
        ),
        "file": file_name,
        "line": line,
    }


def _json_safe_fields(fields: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    try:
        json.dumps(fields)
    except TypeError:
        return _stringify_unserializable(fields), True
    return fields, False


def _stringify_unserializable(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _stringify_unserializable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_stringify_unserializable(item) for item in value]
    if isinstance(value, tuple):
        return [_stringify_unserializable(item) for item in value]
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value
