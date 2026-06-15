"""Pool git versioning: dulwich-backed git-on-disk for the shared skill pool.

The pool directory is a single git repository. Every write path (create / edit /
upload / archive / builtin seed) calls ``commit_pool`` after writing files.
``init_pool`` is idempotent; calling it on an already-initialized repo is a no-op.

All writes are serialized via a cross-process file lock (``<pool>/.git/fleetent.lock``)
so concurrent admin operations and server workers do not corrupt the repo. Reads
(history, diff) do not acquire the lock.
"""

from __future__ import annotations

import contextlib
import io
import os
import time
from pathlib import Path
from typing import Any

_SYSTEM_AUTHOR = b"system <system@fleetent>"
_DIFF_SIZE_LIMIT = 256 * 1024  # 256 KiB before degrading to file list


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_git_repo(pool_dir: Path) -> bool:
    return (pool_dir / ".git").is_dir()


def _lock_path(pool_dir: Path) -> Path:
    return pool_dir / ".git" / "fleetent.lock"


class _FileLock:
    """Cross-process exclusive file lock using O_CREAT|O_EXCL spin."""

    def __init__(self, path: Path, timeout: float = 30.0, poll: float = 0.05) -> None:
        self._path = path
        self._timeout = timeout
        self._poll = poll

    def __enter__(self) -> _FileLock:
        deadline = time.monotonic() + self._timeout
        while True:
            try:
                fd = os.open(str(self._path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.close(fd)
                return self
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise TimeoutError(f"could not acquire pool lock {self._path}") from None
                time.sleep(self._poll)

    def __exit__(self, *_: Any) -> None:
        with contextlib.suppress(OSError):
            self._path.unlink(missing_ok=True)


def _has_staged_changes(pool_dir: Path) -> bool:
    """Return True if the index differs from HEAD (i.e. there is something to commit)."""
    from dulwich.diff_tree import tree_changes
    from dulwich.repo import Repo

    r = Repo(str(pool_dir))
    index = r.open_index()
    index_tree_id = index.commit(r.object_store)

    try:
        head_commit: Any = r[r.head()]
        head_tree = head_commit.tree
    except Exception:
        # No HEAD yet — any staged content counts as a change
        return True

    changes = list(tree_changes(r.object_store, head_tree, index_tree_id))
    return len(changes) > 0


def _stage_paths(pool_dir: Path, skill_name: str | None = None) -> None:
    """Stage files under pool_dir for commit.

    If ``skill_name`` is given, stage only that skill's subtree so concurrent
    writes to different skills each produce their own commit. Otherwise stage all.
    """
    from dulwich import porcelain

    if skill_name is not None:
        skill_dir = pool_dir / skill_name
        paths: list[str] = []
        if skill_dir.is_dir():
            for p in skill_dir.rglob("*"):
                if p.is_file():
                    paths.append(str(p.relative_to(pool_dir)))
        if paths:
            porcelain.add(str(pool_dir), paths)
        # Also stage deletions in that skill's subtree
        from dulwich.repo import Repo

        try:
            r = Repo(str(pool_dir))
            index = r.open_index()
            prefix = (skill_name + "/").encode()
            for tracked in list(index):
                if tracked.startswith(prefix):
                    full = pool_dir / tracked.decode()
                    if not full.exists():
                        del index[tracked]
            index.write()
        except Exception:
            pass
    else:
        porcelain.add(str(pool_dir))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def init_pool(pool_dir: Path) -> None:
    """Idempotently initialize ``pool_dir`` as a git repository.

    If already a git repo, does nothing. Otherwise runs git init, stages all
    current content, and commits as the initial commit (skips commit if empty).
    """
    from dulwich import porcelain

    if _is_git_repo(pool_dir):
        return

    pool_dir.mkdir(parents=True, exist_ok=True)
    porcelain.init(str(pool_dir))

    # Check for any content to commit (excluding .git itself)
    has_content = any(
        fname
        for dirpath, dirnames, filenames in os.walk(str(pool_dir))
        for _ in [dirnames.__setitem__(slice(None), [d for d in dirnames if d != ".git"])]
        for fname in filenames
    )

    if not has_content:
        return

    _stage_paths(pool_dir)
    if _has_staged_changes(pool_dir):
        porcelain.commit(
            str(pool_dir),
            message=b"seed: initialize pool from existing skills",
            author=_SYSTEM_AUTHOR,
            committer=_SYSTEM_AUTHOR,
        )


def commit_pool(
    pool_dir: Path, *, message: str, author: str, skill_name: str | None = None
) -> str | None:
    """Stage changes and commit to the pool repo.

    If ``skill_name`` is given, stage only that skill's subtree so concurrent
    writes to different skills each produce their own commit. Otherwise stages all.
    Returns the new commit sha hex string, or None if nothing to commit.
    Serialized by cross-process file lock to prevent concurrent write corruption.
    """
    from dulwich import porcelain

    with _FileLock(_lock_path(pool_dir)):
        _stage_paths(pool_dir, skill_name)
        if not _has_staged_changes(pool_dir):
            return None
        sha = porcelain.commit(
            str(pool_dir),
            message=message.encode(),
            author=author.encode(),
            committer=author.encode(),
        )
        return sha.decode() if isinstance(sha, bytes) else sha


def pool_version_for_skill(pool_dir: Path, skill_name: str) -> str | None:
    """Return the last commit sha (hex) that touched ``<pool_dir>/<skill_name>/``.

    Returns None if no commits exist for this skill yet.
    """
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
    except Exception:
        return None

    try:
        for entry in r.get_walker(paths=[skill_name.encode()]):
            return entry.commit.id.decode()
    except Exception:
        pass
    return None


def pool_skill_history(
    pool_dir: Path, skill_name: str, max_entries: int = 50
) -> list[dict[str, Any]]:
    """Return commit history for ``skill_name`` in reverse chronological order.

    Each entry: ``{"sha", "message", "author", "timestamp"}``.
    """
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
    except Exception:
        return []

    result: list[dict[str, Any]] = []
    try:
        for entry in r.get_walker(paths=[skill_name.encode()], max_entries=max_entries):
            result.append(
                {
                    "sha": entry.commit.id.decode(),
                    "message": entry.commit.message.decode(errors="replace").strip(),
                    "author": entry.commit.author.decode(errors="replace"),
                    "timestamp": entry.commit.author_time,
                }
            )
    except Exception:
        pass
    return result


def pool_diff_for_commit(pool_dir: Path, skill_name: str, ref: str) -> dict[str, Any]:
    """Return the unified diff for ``ref`` relative to its parent commit.

    If diff exceeds ``_DIFF_SIZE_LIMIT`` bytes, degrades to a list of changed
    file names with ``truncated=True`` — never silently truncates.

    Returns ``{"diff": str, "truncated": bool, "changed_files": list[str]}``.
    """
    from dulwich.diff_tree import tree_changes
    from dulwich.patch import write_tree_diff
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
    except Exception:
        return {"diff": "", "truncated": False, "changed_files": [], "error": "no repo"}

    try:
        commit: Any = r[ref.encode()]
    except Exception:
        return {
            "diff": "",
            "truncated": False,
            "changed_files": [],
            "error": f"ref {ref!r} not found",
        }

    parent_tree = None
    if commit.parents:
        try:
            parent: Any = r[commit.parents[0]]
            parent_tree = parent.tree
        except Exception:
            pass

    out = io.BytesIO()
    try:
        write_tree_diff(out, r.object_store, parent_tree, commit.tree)
    except Exception as exc:
        return {"diff": "", "truncated": False, "changed_files": [], "error": str(exc)}

    raw = out.getvalue()

    # Collect changed files scoped to the skill subtree
    skill_prefix = skill_name + "/"
    changed_files: list[str] = []
    try:
        for change in tree_changes(r.object_store, parent_tree, commit.tree):
            new_path = change.new.path if change.new is not None else None
            old_path = change.old.path if change.old is not None else None
            path = (new_path or old_path or b"").decode(errors="replace")
            if path.startswith(skill_prefix) or path == skill_name:
                changed_files.append(path)
    except Exception:
        pass

    if len(raw) > _DIFF_SIZE_LIMIT:
        return {
            "diff": "",
            "truncated": True,
            "changed_files": changed_files,
            "warning": (
                f"diff exceeds {_DIFF_SIZE_LIMIT // 1024} KiB; showing changed file names only"
            ),
        }

    return {
        "diff": raw.decode(errors="replace"),
        "truncated": False,
        "changed_files": changed_files,
    }


def pool_content_at(pool_dir: Path, skill_name: str, ref: str) -> str | None:
    """Return the SKILL.md content for ``skill_name`` at git ref ``ref``.

    Returns None if not found at that ref.
    """
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
        commit: Any = r[ref.encode()]
        tree: Any = r.object_store[commit.tree]
        for item in tree.items():
            if item.path.decode() == skill_name:
                subtree: Any = r.object_store[item.sha]
                for subitem in subtree.items():
                    if subitem.path.decode() == "SKILL.md":
                        blob: Any = r.object_store[subitem.sha]
                        return str(blob.data.decode(errors="replace"))
    except Exception:
        pass
    return None


def pool_bundle_at(pool_dir: Path, skill_name: str, ref: str) -> dict[str, str] | None:
    """Return the full skill bundle for ``skill_name`` at git ref ``ref``."""
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
        commit: Any = r[ref.encode()]
        tree: Any = r.object_store[commit.tree]
        for item in tree.items():
            if item.path.decode() != skill_name:
                continue
            subtree: Any = r.object_store[item.sha]
            bundle: dict[str, str] = {}

            def _walk(prefix: str, node: Any, out: dict[str, str]) -> None:
                for subitem in node.items():
                    name = subitem.path.decode()
                    child = r.object_store[subitem.sha]
                    relpath = f"{prefix}{name}"
                    if hasattr(child, "items"):
                        _walk(relpath + "/", child, out)
                    else:
                        blob_data = getattr(child, "data", b"")
                        out[relpath] = str(blob_data.decode(errors="replace"))

            _walk("", subtree, bundle)
            return bundle
    except Exception:
        pass
    return None


def backfill_current_versions(pool_dir: Path, update_fn: Any) -> None:
    """Backfill ``current_version`` for every skill in the pool after init.

    ``update_fn(skill_name: str, version: str)`` is called for each skill.
    Typically wired to ``skill_admin_store.set_current_version``.
    """
    if not _is_git_repo(pool_dir):
        return
    for skill_dir in sorted(p for p in pool_dir.iterdir() if p.is_dir() and p.name != ".git"):
        version = pool_version_for_skill(pool_dir, skill_dir.name)
        if version is not None:
            update_fn(skill_dir.name, version)
