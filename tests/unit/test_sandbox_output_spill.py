"""Tests for sandbox large-output spill (sandbox-large-output-spill).

Spill files are an injectable file boundary (SANDBOX_OUTPUT_DIR monkeypatched to
tmp_path), so these stay unit-level. cap_or_spill writes exactly the text it is given
(the caller redacts before calling), and prunes expired files on write.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from fleetent.integrations.sandbox import output_spill


@pytest.fixture(autouse=True)
def spill_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    d = tmp_path / "sandbox_output"
    monkeypatch.setattr(output_spill, "SANDBOX_OUTPUT_DIR", d)
    return d


def test_under_budget_returns_unchanged_and_writes_no_file(spill_dir: Path) -> None:
    text = "small output that fits"
    out = output_spill.cap_or_spill(text, 1000, label="stdout")
    assert out == text
    assert not list(spill_dir.glob("*.txt"))


def test_over_budget_spills_full_content_and_returns_reference(spill_dir: Path) -> None:
    text = "A" * 5000
    out = output_spill.cap_or_spill(text, 1000, label="stdout")

    files = list(spill_dir.glob("*.txt"))
    assert len(files) == 1
    assert files[0].read_text() == text  # full content preserved on disk
    assert str(files[0]) in out  # path referenced in the return value
    assert "read_file" in out  # hint to read the full output
    assert "5000" in out  # original byte count surfaced
    assert "A" in out  # a head/tail preview is included


def test_spill_writes_exactly_the_text_passed(spill_dir: Path) -> None:
    """cap_or_spill does not redact — it writes what it is given (caller redacts first)."""
    text = "B" * 3000
    output_spill.cap_or_spill(text, 500, label="stderr")
    files = list(spill_dir.glob("*.txt"))
    assert files[0].read_text() == text


def test_cleanup_removes_expired_spill_on_write(spill_dir: Path) -> None:
    spill_dir.mkdir(parents=True)
    old = spill_dir / "old.txt"
    old.write_text("stale")
    eight_days_ago = time.time() - 8 * 24 * 3600
    os.utime(old, (eight_days_ago, eight_days_ago))

    output_spill.cap_or_spill("C" * 3000, 500, label="stdout")

    assert not old.exists()  # expired file pruned on write
    assert len(list(spill_dir.glob("*.txt"))) == 1  # only the new spill remains


def test_cleanup_keeps_recent_spill_on_write(spill_dir: Path) -> None:
    spill_dir.mkdir(parents=True)
    recent = spill_dir / "recent.txt"
    recent.write_text("fresh")

    output_spill.cap_or_spill("D" * 3000, 500, label="stdout")

    assert recent.exists()  # within retention -> kept


def test_public_api_exports_cap_or_spill() -> None:
    from fleetent.integrations.sandbox import cap_or_spill as exported

    assert exported is output_spill.cap_or_spill
