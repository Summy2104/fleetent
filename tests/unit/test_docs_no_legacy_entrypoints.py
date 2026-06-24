"""Static check: current docs/Makefile/scripts must not reference legacy entrypoints.

Legacy entrypoints that must NOT appear as user-facing CLI instructions in
current (non-archive) docs:
  - fleetent admin ...  (renamed to fleetent platform)
  - bare uvicorn fleetent.server:app  (replaced by fleetent platform serve)
  - bare python scripts/upgrade.py   (replaced by fleetent platform upgrade)
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).parents[2]

_CURRENT_DOC_DIRS = [
    _REPO_ROOT / "docs",
    _REPO_ROOT / "README.md",
    _REPO_ROOT / "Makefile",
]

_ARCHIVE_PATTERNS = [
    re.compile(r"docs/archive"),
    re.compile(r"docs/records"),   # historical integration records, not current operational docs
    re.compile(r"openspec/changes/archive"),
]

_LEGACY_PATTERNS = [
    # fleetent admin <command> — CLI namespace removed
    re.compile(r"\bfleetent admin\b"),
    # bare uvicorn invocation as main serve entrypoint
    re.compile(r"\buvicorn fleetent\.server:app\b"),
    re.compile(r"\bpython -m uvicorn fleetent\.server:app\b"),
    # bare scripts/upgrade.py as user-facing upgrade command
    re.compile(r"\bscripts/upgrade\.py\b"),
]

# Allowed exceptions: comment lines, historical notes in non-archive docs, AGENTS.md
_ALLOWED_CONTEXTS = [
    re.compile(r"^\s*#"),                       # comment line
    re.compile(r"^>"),                          # blockquote (historical note in design docs)
    re.compile(r"^\s*-\s*\*\*Breaking"),        # design doc risk section
    re.compile(r"技术上仍可用"),                 # explicit "still works technically" note
    re.compile(r"scripts/upgrade\.py.*可保留"),  # design doc noting script can stay
    re.compile(r"scripts/upgrade\.py.*实现载体"),
    re.compile(r"scripts/upgrade\.py.*short"),
    re.compile(r"scripts/upgrade\.py.*保留"),
    re.compile(r"scripts/upgrade\.py.*底层"),
    re.compile(r"scripts/upgrade\.py.*内部"),
    re.compile(r"scripts/upgrade\.py.*thin"),
    re.compile(r"scripts/upgrade\.py.*兼容"),
    re.compile(r"scripts\.upgrade"),            # python import path in source
    # uvicorn still works as a bare ASGI app; allowed when line explicitly says dev-mode/ASGI-direct
    re.compile(r"仅用于开发模式"),
    re.compile(r"只作为开发模式"),
    re.compile(r"ASGI 应用"),
    re.compile(r"ASGI app"),
    re.compile(r"开发模式补充"),
    # "fleetent admin 身份" — admin used as a role/identity noun, not CLI command
    re.compile(r"admin 身份"),
    # intelligence roadmap doc mentions uvicorn as non-recommended dev alternative
    re.compile(r"推荐仍使用"),
]


def _collect_doc_files() -> list[Path]:
    files: list[Path] = []
    for entry in _CURRENT_DOC_DIRS:
        if entry.is_file():
            files.append(entry)
        elif entry.is_dir():
            for ext in ("*.md", "*.sh", "*.yaml", "*.yml"):
                files.extend(entry.rglob(ext))
    return files


def _is_archive(path: Path) -> bool:
    path_str = str(path)
    return any(pat.search(path_str) for pat in _ARCHIVE_PATTERNS)


def _line_is_allowed(line: str) -> bool:
    return any(pat.search(line) for pat in _ALLOWED_CONTEXTS)


def test_no_legacy_entrypoints_in_current_docs() -> None:
    violations: list[str] = []

    for doc_file in _collect_doc_files():
        if _is_archive(doc_file):
            continue
        rel = doc_file.relative_to(_REPO_ROOT)
        lines = doc_file.read_text(encoding="utf-8", errors="replace").splitlines()
        for lineno, line in enumerate(lines, start=1):
            if _line_is_allowed(line):
                continue
            for pat in _LEGACY_PATTERNS:
                if pat.search(line):
                    violations.append(f"{rel}:{lineno}: {line.strip()}")
                    break

    assert not violations, (
        "Legacy CLI entrypoints found in current docs/Makefile:\n"
        + "\n".join(f"  {v}" for v in violations)
    )
