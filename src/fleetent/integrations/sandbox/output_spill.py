"""Spill over-budget sandbox output to disk and return a reference (large-output-spill).

`run_code` previously dropped the middle of over-budget output (head+tail truncation).
This module instead writes the full output to a file under ``SANDBOX_OUTPUT_DIR`` and
returns a head+tail preview plus a reference (path, original size, "read with read_file"),
so the model can fetch the complete output on demand without bloating the context.

Caller contract: redact BEFORE calling — ``cap_or_spill`` writes exactly the text it is
given, so secrets must already be removed (no credentials on disk). The spill directory is
self-bounding: expired files are pruned opportunistically on each write (no scheduler).
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

from fleetent import paths
from fleetent.integrations.sandbox.output_truncation import truncate_stream
from fleetent.observability.structured_logging import get_logger

_logger = get_logger("sandbox.output_spill")

# Spill directory + retention. Injectable module-level constants (no global mutable
# state): tests monkeypatch SANDBOX_OUTPUT_DIR to a tmp path. Mirrors the
# builtin_tools.GENERATED_DIR / UPLOADS_DIR convention (paths.data_dir()/<name>).
SANDBOX_OUTPUT_DIR: Path = paths.data_dir() / "sandbox_output"
SPILL_RETENTION_SECONDS: float = 7 * 24 * 3600.0

_REF_NOTICE = "\n[完整 {label} 输出已落盘：{path}（{orig} 字节），可用 read_file 读取完整内容]"


def cap_or_spill(text: str, max_bytes: int, *, label: str) -> str:
    """Return ``text`` if within budget, else spill the full text and return preview+ref.

    Within budget → returned unchanged (no file written). Over budget → the full ``text``
    is written to a spill file and the return value is a head+tail preview (via
    ``truncate_stream``) followed by a reference line naming the file, its original byte
    size, and that it can be read with ``read_file``. ``text`` is written verbatim — the
    caller is responsible for redacting first.
    """
    orig = len(text.encode("utf-8"))
    if orig <= max_bytes:
        return text
    path = _write_spill(text)
    preview = truncate_stream(text, max_bytes)
    return preview + _REF_NOTICE.format(label=label, path=path, orig=orig)


def _write_spill(text: str) -> Path:
    """Write ``text`` to a uuid-named file under SANDBOX_OUTPUT_DIR, pruning expired first."""
    SANDBOX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _cleanup_expired()
    path = SANDBOX_OUTPUT_DIR / f"{uuid.uuid4().hex}.txt"
    path.write_text(text, encoding="utf-8")
    _logger.info("sandbox_output_spilled", path=str(path), bytes=len(text.encode("utf-8")))
    return path


def _cleanup_expired() -> None:
    """Prune spill files older than the retention window. Best-effort; never raises."""
    cutoff = time.time() - SPILL_RETENTION_SECONDS
    try:
        entries = list(SANDBOX_OUTPUT_DIR.glob("*.txt"))
    except OSError as exc:
        _logger.warn("sandbox_spill_cleanup_scan_failed", error=str(exc))
        return
    for entry in entries:
        try:
            if entry.stat().st_mtime < cutoff:
                entry.unlink(missing_ok=True)
        except OSError as exc:
            _logger.warn("sandbox_spill_cleanup_unlink_failed", path=str(entry), error=str(exc))
