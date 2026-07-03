"""Pool git versioning: dulwich-backed git-on-disk for the shared skill pool.

The pool directory is a single git repository. Every local write path (create / edit /
upload / archive / builtin seed) calls ``commit_pool`` after writing files.
``init_pool`` is idempotent; calling it on an already-initialized repo is a no-op.

The pool MAY also be bound to an external git remote and driven as its local mirror
(``init_pool_with_remote`` + ``fetch_remote`` + ``reset_pool_to``): the external repo is
authoritative and the pool is reset --hard onto the fetched commit (GitOps inbound).

All writes are serialized via a cross-process file lock (``<pool>/.git/fleetent.lock``)
so concurrent admin operations and server workers do not corrupt the repo. Reads
(history, diff) do not acquire the lock.
"""

from __future__ import annotations

import contextlib
import io
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_SYSTEM_AUTHOR = b"system <system@fleetent>"
_DIFF_SIZE_LIMIT = 256 * 1024  # 256 KiB before degrading to file list
_MIRROR_FETCH_DEPTH = 1  # the pool only mirrors the branch tip; history is never needed


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_git_repo(pool_dir: Path) -> bool:
    return (pool_dir / ".git").is_dir()


def _skill_tree_path(subdir: str, name: str) -> str:
    """Map a clean skill name to its git tree path under the optional scan subdir.

    Empty ``subdir`` returns ``name`` unchanged (flat layout, git root == scan
    root); a non-empty ``subdir`` prefixes it as ``<subdir>/<name>``.
    """
    if not subdir:
        return name
    return f"{subdir}/{name}"


def resolve_git_root(scan_dir: Path, subdir: str) -> Path:
    """Invert scan root → git root by stripping the ``skills_subdir`` suffix.

    The pool's git root (where ``.git`` lives and ``reset --hard`` operates) is the
    external repo root, while the skill *scan* root may be a subdirectory of it
    (``<repo>/<subdir>``). This is the single canonical implementation of that
    inversion; all platform-side callers reuse it rather than re-deriving the git
    root with ad-hoc string surgery.

    Args:
        scan_dir: The skill scan root (``FLEETENT_SKILLS_DIR``).
        subdir: The configured ``skills_subdir`` (``""`` when scan root == git root).

    Returns:
        The git repository root. When ``subdir`` is empty, ``scan_dir`` unchanged.
        When ``scan_dir`` ends with ``/<subdir>``, the parent obtained by stripping
        that suffix. On mismatch (misconfiguration) this degrades safely: it logs a
        warning and returns ``scan_dir`` itself rather than raising — never letting a
        bad config silently point ``reset --hard`` at the wrong directory.
    """
    if not subdir:
        return scan_dir

    subdir_parts = Path(subdir).parts
    scan_parts = scan_dir.parts
    if len(scan_parts) >= len(subdir_parts) and scan_parts[-len(subdir_parts) :] == subdir_parts:
        return Path(*scan_parts[: -len(subdir_parts)])

    logger.warning(
        "skills scan root %s does not end with configured skills_subdir %r; "
        "falling back to treating the scan root as the git root",
        scan_dir,
        subdir,
    )
    return scan_dir


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

    with Repo(str(pool_dir)) as r:
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


def _stage_paths(pool_dir: Path, skill_name: str | None = None, *, subdir: str = "") -> None:
    """Stage files under pool_dir for commit.

    If ``skill_name`` is given, stage only that skill's subtree so concurrent
    writes to different skills each produce their own commit. Otherwise stage all
    content under ``subdir`` (or the whole ``pool_dir`` when ``subdir`` is empty).
    ``subdir`` prefixes the skill's git tree path when the scan root lives under a
    subdirectory of the git root — both the filesystem walk and the deletion-prefix
    check operate on ``<subdir>/<name>`` so the staged range matches the committed
    subtree exactly (R3). Scoping the "stage all" branch to ``subdir`` matters
    whenever the git root is a real repo checkout that is also FLEETENT_HOME itself
    (skills_subdir configurations commonly resolve the git root that way): staging
    the unscoped ``pool_dir`` would sweep up the platform's own runtime files
    (management.db, .env, node/, logs/, tenants/) into the pool repo.
    """
    from dulwich import porcelain

    if skill_name is not None:
        tree_path = _skill_tree_path(subdir, skill_name)
        skill_dir = pool_dir / tree_path
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
            with Repo(str(pool_dir)) as r:
                index = r.open_index()
                prefix = (tree_path + "/").encode()
                for tracked in list(index):
                    if tracked.startswith(prefix):
                        full = pool_dir / tracked.decode()
                        if not full.exists():
                            del index[tracked]
                index.write()
        except Exception:
            pass
    elif subdir:
        porcelain.add(str(pool_dir), [subdir])
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
    pool_dir: Path,
    *,
    message: str,
    author: str,
    skill_name: str | None = None,
    subdir: str = "",
) -> str | None:
    """Stage changes and commit to the pool repo.

    If ``skill_name`` is given, stage only that skill's subtree so concurrent
    writes to different skills each produce their own commit. Otherwise stages all.
    ``subdir`` prefixes the skill's git tree path when the scan root lives under a
    subdirectory of the git root (``pool_dir``); empty ``subdir`` is the flat layout.
    Returns the new commit sha hex string, or None if nothing to commit.
    Serialized by cross-process file lock to prevent concurrent write corruption.
    """
    from dulwich import porcelain

    with _FileLock(_lock_path(pool_dir)):
        _stage_paths(pool_dir, skill_name, subdir=subdir)
        if not _has_staged_changes(pool_dir):
            return None
        sha = porcelain.commit(
            str(pool_dir),
            message=message.encode(),
            author=author.encode(),
            committer=author.encode(),
        )
        return sha.decode() if isinstance(sha, bytes) else sha


def pool_version_for_skill(pool_dir: Path, skill_name: str, *, subdir: str = "") -> str | None:
    """Return the last commit sha (hex) that touched the skill's subtree.

    The subtree is ``<pool_dir>/<subdir>/<skill_name>/`` (or ``<pool_dir>/<skill_name>/``
    when ``subdir`` is empty). ``pool_dir`` is the git root. Returns None if no commits
    exist for this skill yet.
    """
    from dulwich.repo import Repo

    try:
        repo = Repo(str(pool_dir))
    except Exception:
        return None

    with repo as r:
        tree_path = _skill_tree_path(subdir, skill_name)
        try:
            for entry in r.get_walker(paths=[tree_path.encode()]):
                return entry.commit.id.decode()
        except Exception:
            pass
    return None


def pool_skill_history(
    pool_dir: Path, skill_name: str, max_entries: int = 50, *, subdir: str = ""
) -> list[dict[str, Any]]:
    """Return commit history for ``skill_name`` in reverse chronological order.

    ``pool_dir`` is the git root; ``subdir`` prefixes the skill's git tree path.
    Each entry: ``{"sha", "message", "author", "timestamp"}``.
    """
    from dulwich.repo import Repo

    try:
        repo = Repo(str(pool_dir))
    except Exception:
        return []

    with repo as r:
        tree_path = _skill_tree_path(subdir, skill_name)
        result: list[dict[str, Any]] = []
        try:
            for entry in r.get_walker(paths=[tree_path.encode()], max_entries=max_entries):
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


def pool_diff_for_commit(
    pool_dir: Path, skill_name: str, ref: str, *, subdir: str = ""
) -> dict[str, Any]:
    """Return the unified diff for ``ref`` relative to its parent commit.

    ``pool_dir`` is the git root; ``subdir`` prefixes the skill's git tree path so
    ``changed_files`` is scoped to that subtree. If diff exceeds ``_DIFF_SIZE_LIMIT``
    bytes, degrades to a list of changed file names with ``truncated=True`` — never
    silently truncates.

    Returns ``{"diff": str, "truncated": bool, "changed_files": list[str]}``.
    """
    from dulwich.diff_tree import tree_changes
    from dulwich.patch import write_tree_diff
    from dulwich.repo import Repo

    try:
        repo = Repo(str(pool_dir))
    except Exception:
        return {"diff": "", "truncated": False, "changed_files": [], "error": "no repo"}

    with repo as r:
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
        tree_path = _skill_tree_path(subdir, skill_name)
        skill_prefix = tree_path + "/"
        changed_files: list[str] = []
        try:
            for change in tree_changes(r.object_store, parent_tree, commit.tree):
                new_path = change.new.path if change.new is not None else None
                old_path = change.old.path if change.old is not None else None
                path = (new_path or old_path or b"").decode(errors="replace")
                if path.startswith(skill_prefix) or path == tree_path:
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


def _descend_to_tree(object_store: Any, root_tree: Any, tree_path: str) -> Any | None:
    """Walk one tree level per ``/``-separated segment of ``tree_path``.

    Returns the tree object for the final segment, or None if any segment is
    missing or resolves to a non-tree entry. This lets ``skills/foo`` reach the
    ``foo`` subtree by descending root → ``skills`` → ``foo`` instead of matching
    a single top-level entry name.
    """
    node = root_tree
    for segment in tree_path.split("/"):
        found = None
        for item in node.items():
            if item.path.decode() == segment:
                found = object_store[item.sha]
                break
        if found is None or not hasattr(found, "items"):
            return None
        node = found
    return node


def pool_content_at(pool_dir: Path, skill_name: str, ref: str, *, subdir: str = "") -> str | None:
    """Return the SKILL.md content for ``skill_name`` at git ref ``ref``.

    ``pool_dir`` is the git root; ``subdir`` prefixes the skill's git tree path.
    Returns None if not found at that ref.
    """
    from dulwich.repo import Repo

    try:
        repo = Repo(str(pool_dir))
    except Exception:
        return None

    with repo as r:
        try:
            commit: Any = r[ref.encode()]
            tree: Any = r.object_store[commit.tree]
            tree_path = _skill_tree_path(subdir, skill_name)
            subtree = _descend_to_tree(r.object_store, tree, tree_path)
            if subtree is None:
                return None
            for subitem in subtree.items():
                if subitem.path.decode() == "SKILL.md":
                    blob: Any = r.object_store[subitem.sha]
                    return str(blob.data.decode(errors="replace"))
        except Exception:
            pass
    return None


def pool_bundle_at(
    pool_dir: Path, skill_name: str, ref: str, *, subdir: str = ""
) -> dict[str, str] | None:
    """Return the full skill bundle for ``skill_name`` at git ref ``ref``.

    ``pool_dir`` is the git root; ``subdir`` prefixes the skill's git tree path.
    Bundle keys are relative to the skill directory (no subdir prefix) so the
    returned names stay clean regardless of the on-disk layout.
    """
    from dulwich.repo import Repo

    try:
        repo = Repo(str(pool_dir))
    except Exception:
        return None

    with repo as r:
        try:
            commit: Any = r[ref.encode()]
            tree: Any = r.object_store[commit.tree]
            tree_path = _skill_tree_path(subdir, skill_name)
            subtree = _descend_to_tree(r.object_store, tree, tree_path)
            if subtree is None:
                return None
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


# ---------------------------------------------------------------------------
# Remote mirror sync (GitOps inbound)
# ---------------------------------------------------------------------------


def init_pool_with_remote(pool_dir: Path, remote_url: str) -> None:
    """Init the pool as a git repo if needed and configure ``origin`` → ``remote_url``.

    Idempotent: re-running updates the configured origin url. Credentials are NOT stored
    here; they are passed per-fetch (see ``fetch_remote``).
    """
    from dulwich import porcelain
    from dulwich.repo import Repo

    if not _is_git_repo(pool_dir):
        pool_dir.mkdir(parents=True, exist_ok=True)
        porcelain.init(str(pool_dir))
    repo = Repo(str(pool_dir))
    try:
        config = repo.get_config()
        config.set((b"remote", b"origin"), b"url", remote_url.encode())
        config.set((b"remote", b"origin"), b"fetch", b"+refs/heads/*:refs/remotes/origin/*")
        config.write_to_path()
    finally:
        repo.close()


def get_remote_head(
    remote_url: str,
    branch: str,
    *,
    username: str | None = None,
    password: str | None = None,
) -> str | None:
    """Return the remote branch tip sha via a refs-only ls-remote (no object transfer).

    A cheap probe (transfers only the ref advertisement, not objects) used to skip the
    full ``fetch_remote`` of a large mirror when the branch tip is unchanged. Returns None
    if the branch is absent or the probe fails, so the caller falls back to a real fetch.
    Credentials apply to http(s) remotes; ssh remotes authenticate via the agent's key.
    """
    from dulwich import porcelain

    ref = b"refs/heads/" + branch.encode()
    try:
        result: Any = porcelain.ls_remote(remote_url)
    except TypeError:
        # Older/newer dulwich signatures may reject positional-only; retry via keyword.
        result = porcelain.ls_remote(remote=remote_url)
    # dulwich 1.2+ returns an LsRemoteResult; treating it as a dict is deprecated. Prefer
    # ``.refs``, falling back to the object itself for older builds that returned a mapping.
    refs = getattr(result, "refs", result)
    sha = refs.get(ref) if refs else None
    if sha is None:
        return None
    return sha.decode() if isinstance(sha, bytes) else str(sha)


def fetch_remote(
    pool_dir: Path,
    *,
    remote_url: str,
    branch: str,
    username: str | None = None,
    password: str | None = None,
) -> str:
    """Fetch ``branch`` from ``remote_url`` and return its commit sha (hex).

    Fetches objects into the pool's object store and reads the target branch sha from the
    fetch result; does NOT touch the working tree (use ``reset_pool_to``). Serialized by the
    pool write lock so a concurrent ``commit_pool`` cannot interleave.

    Raises:
        ValueError: if ``branch`` does not exist on the remote.
    """
    from dulwich import porcelain

    ref = b"refs/heads/" + branch.encode()
    with _FileLock(_lock_path(pool_dir)):
        try:
            # Shallow: the pool only ever resets to the branch tip, so history is dead weight.
            # A full fetch of a large mirror (5000+ commits, 100MB+ pack) is what made the
            # first sync crawl; depth=1 pulls just the tip commit + trees. An incremental
            # depth=1 fetch advances the shallow boundary to the new tip.
            result = porcelain.fetch(
                str(pool_dir),
                remote_url,
                username=username or None,
                password=password or None,
                depth=_MIRROR_FETCH_DEPTH,
            )
        except TypeError:
            # dulwich build without a ``depth`` kwarg — fall back to a full fetch.
            result = porcelain.fetch(
                str(pool_dir),
                remote_url,
                username=username or None,
                password=password or None,
            )
        refs_map: Any = result.refs
        sha = refs_map.get(ref)
    if sha is None:
        raise ValueError(f"branch {branch!r} not found on remote {remote_url!r}")
    return sha.decode() if isinstance(sha, bytes) else str(sha)


def reset_pool_to(pool_dir: Path, sha: str) -> None:
    """Hard-reset the pool's working tree and current branch to commit ``sha``.

    Moves the current branch ref to ``sha`` (so per-skill version reads resolve against the
    mirrored commit) then ``reset --hard`` to align the working tree. The commit must already
    be in the object store (fetched via ``fetch_remote``). Serialized by the pool write lock.
    """
    from dulwich import porcelain
    from dulwich.repo import Repo

    sha_b = sha.encode()
    with _FileLock(_lock_path(pool_dir)):
        repo = Repo(str(pool_dir))
        try:
            refs: Any = repo.refs
            head = refs.read_ref(b"HEAD")
            if head is not None and head.startswith(b"ref: "):
                refs[head[len(b"ref: ") :]] = sha_b
            else:
                refs[b"HEAD"] = sha_b
        finally:
            repo.close()
        porcelain.reset(str(pool_dir), "hard", sha_b)


def list_pool_skills(pool_dir: Path) -> list[str]:
    """Return the skill directory names present in the pool (excludes ``.git``)."""
    if not pool_dir.is_dir():
        return []
    return sorted(p.name for p in pool_dir.iterdir() if p.is_dir() and p.name != ".git")
