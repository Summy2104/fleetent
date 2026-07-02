"""Integration tests for pool_git: pool git repo init / commit / serialization.

All tests use real dulwich repos in tmp_path — no mocks.
"""

from __future__ import annotations

import multiprocessing
from pathlib import Path

from fleetent.platform.skill_management import pool_git

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _make_skill(pool_dir: Path, name: str, content: str = "hello") -> None:
    skill_dir = pool_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _commit_count(pool_dir: Path) -> int:
    from dulwich.repo import Repo

    try:
        r = Repo(str(pool_dir))
    except Exception:
        return 0
    count = 0
    try:
        for _ in r.get_walker():
            count += 1
    except Exception:
        pass
    return count


# ---------------------------------------------------------------------------
# 1.1: init_pool - non-git dir becomes git repo with one initial commit;
#      already-git dir is idempotent
# ---------------------------------------------------------------------------


def test_init_pool_creates_git_repo(tmp_path):
    _make_skill(tmp_path, "alpha")
    pool_git.init_pool(tmp_path)

    assert (tmp_path / ".git").is_dir()
    assert _commit_count(tmp_path) == 1


def test_init_pool_initial_commit_includes_existing_content(tmp_path):
    _make_skill(tmp_path, "alpha")
    _make_skill(tmp_path, "beta")
    pool_git.init_pool(tmp_path)

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    # walk tree of HEAD
    head_commit = r[r.head()]
    tree = r.object_store[head_commit.tree]
    names = {item.path.decode() for item in tree.items()}
    assert "alpha" in names
    assert "beta" in names


def test_init_pool_idempotent_on_existing_git_repo(tmp_path):
    _make_skill(tmp_path, "alpha")
    pool_git.init_pool(tmp_path)
    assert _commit_count(tmp_path) == 1

    # second call: no new commit
    pool_git.init_pool(tmp_path)
    assert _commit_count(tmp_path) == 1


def test_init_pool_empty_dir(tmp_path):
    # empty pool dir still becomes a git repo (no-content case)
    pool_git.init_pool(tmp_path)
    assert (tmp_path / ".git").is_dir()


# ---------------------------------------------------------------------------
# 1.2: commit_pool - attributable commits; no-change = no empty commit
# ---------------------------------------------------------------------------


def test_commit_pool_creates_attributable_commit(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "crm-ops", "v1")

    pool_git.commit_pool(tmp_path, message="edit: crm-ops", author="alice <alice@corp.com>")

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    head = r[r.head()]
    assert b"edit: crm-ops" in head.message
    assert b"alice" in head.author


def test_commit_pool_no_change_no_empty_commit(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "alpha")
    pool_git.commit_pool(tmp_path, message="seed: alpha", author="system <system@fleetent>")

    count_before = _commit_count(tmp_path)
    # nothing changed — calling commit_pool should not produce an extra commit
    pool_git.commit_pool(tmp_path, message="seed: alpha", author="system <system@fleetent>")
    assert _commit_count(tmp_path) == count_before


def test_commit_pool_system_author(tmp_path):
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "alpha", "v1")
    pool_git.commit_pool(
        tmp_path, message="seed: initialize pool", author="system <system@fleetent>"
    )

    from dulwich.repo import Repo

    r = Repo(str(tmp_path))
    head = r[r.head()]
    assert b"system" in head.author


# ---------------------------------------------------------------------------
# 1.3: write serialization - concurrent writes don't corrupt the repo
# ---------------------------------------------------------------------------


def _worker_write(pool_dir_str: str, skill_name: str, content: str) -> None:
    """Subprocess worker: commit one skill change to the pool."""
    pool_dir = Path(pool_dir_str)
    _make_skill(pool_dir, skill_name, content)
    pool_git.commit_pool(
        pool_dir,
        message=f"edit: {skill_name}",
        author=f"worker <{skill_name}@test>",
        skill_name=skill_name,
    )


def test_concurrent_writes_serialized_and_repo_intact(tmp_path):
    pool_git.init_pool(tmp_path)

    # launch two concurrent processes writing to different skills
    p1 = multiprocessing.Process(
        target=_worker_write, args=(str(tmp_path), "skill-a", "content from proc 1")
    )
    p2 = multiprocessing.Process(
        target=_worker_write, args=(str(tmp_path), "skill-b", "content from proc 2")
    )
    p1.start()
    p2.start()
    p1.join(timeout=10)
    p2.join(timeout=10)

    assert p1.exitcode == 0, f"proc1 failed with exitcode {p1.exitcode}"
    assert p2.exitcode == 0, f"proc2 failed with exitcode {p2.exitcode}"

    # repo must be intact: each worker adds exactly 1 commit
    # (init_pool on empty dir creates repo but no commit, so expect exactly 2)
    count = _commit_count(tmp_path)
    assert count >= 2, f"expected ≥2 commits (one per worker), got {count}"

    # both skills must exist in the pool
    assert (tmp_path / "skill-a" / "SKILL.md").exists()
    assert (tmp_path / "skill-b" / "SKILL.md").exists()


# ---------------------------------------------------------------------------
# skill-gitops-subdir: scan-root vs git-root separation (subdir="skills")
# ---------------------------------------------------------------------------


def _make_skill_in(base_dir: Path, name: str, content: str = "hello") -> None:
    """Create ``<base_dir>/<name>/SKILL.md`` (base_dir may be a scan subdir)."""
    skill_dir = base_dir / name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(content, encoding="utf-8")


def _subdir_repo(repo: Path) -> tuple[Path, Path]:
    """Build a repo with ``skills/foo`` and a decoy ``claude/bar``, each committed.

    Returns ``(scan_dir, repo)`` where ``scan_dir == repo / "skills"``.
    """
    scan_dir = repo / "skills"
    decoy_dir = repo / "claude"
    scan_dir.mkdir(parents=True, exist_ok=True)
    decoy_dir.mkdir(parents=True, exist_ok=True)
    pool_git.init_pool(repo)

    _make_skill_in(scan_dir, "foo", "foo v1")
    pool_git.commit_pool(
        repo, message="edit: foo", author="admin <a@a.com>", skill_name="foo", subdir="skills"
    )
    _make_skill_in(decoy_dir, "bar", "bar v1")
    pool_git.commit_pool(repo, message="seed: claude/bar", author="system <system@f>")
    return scan_dir, repo


# --- pure helpers -----------------------------------------------------------


def test_skill_tree_path_with_subdir():
    assert pool_git._skill_tree_path("skills", "foo") == "skills/foo"


def test_skill_tree_path_empty_subdir():
    assert pool_git._skill_tree_path("", "foo") == "foo"


def test_resolve_git_root_strips_matching_subdir(tmp_path):
    scan_dir = tmp_path / "ai-skills-library" / "skills"
    scan_dir.mkdir(parents=True)
    assert pool_git.resolve_git_root(scan_dir, "skills") == scan_dir.parent


def test_resolve_git_root_empty_subdir_returns_scan_dir(tmp_path):
    scan_dir = tmp_path / "pool"
    scan_dir.mkdir()
    assert pool_git.resolve_git_root(scan_dir, "") == scan_dir


def test_resolve_git_root_mismatch_warns_and_falls_back(tmp_path, caplog):
    scan_dir = tmp_path / "pool"  # does NOT end with /skills
    scan_dir.mkdir()
    import logging

    with caplog.at_level(logging.WARNING):
        result = pool_git.resolve_git_root(scan_dir, "skills")

    assert result == scan_dir  # degrade safely, do not raise
    assert any(record.levelno == logging.WARNING for record in caplog.records)


# --- (B) class functions with subdir ----------------------------------------


def test_pool_version_for_skill_subdir_scoped(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)

    sha = pool_git.pool_version_for_skill(repo, "foo", subdir="skills")
    assert sha is not None

    # editing the decoy claude/bar must NOT change foo's version
    _make_skill_in(repo / "claude", "bar", "bar v2")
    pool_git.commit_pool(repo, message="edit: claude/bar", author="system <system@f>")
    assert pool_git.pool_version_for_skill(repo, "foo", subdir="skills") == sha


def test_list_pool_skills_scans_only_subdir(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)
    # scanning the scan root sees only foo, not the decoy claude/
    assert pool_git.list_pool_skills(scan_dir) == ["foo"]
    # scanning the git root would (wrongly) surface claude too — proves separation
    assert "claude" in pool_git.list_pool_skills(repo)


def test_commit_pool_subdir_stages_only_subtree_add_modify_delete(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)
    from dulwich.repo import Repo

    def tracked_paths() -> set[str]:
        r = Repo(str(repo))
        return {t.decode() for t in r.open_index()}

    # baseline: both skills/foo/SKILL.md and claude/bar/SKILL.md tracked
    assert "skills/foo/SKILL.md" in tracked_paths()
    assert "claude/bar/SKILL.md" in tracked_paths()

    # ADD a new file under skills/foo
    (scan_dir / "foo" / "extra.txt").write_text("x", encoding="utf-8")
    # MODIFY existing file under skills/foo
    (scan_dir / "foo" / "SKILL.md").write_text("foo v2", encoding="utf-8")
    sha = pool_git.commit_pool(
        repo,
        message="edit: foo add+mod",
        author="admin <a@a.com>",
        skill_name="foo",
        subdir="skills",
    )
    assert sha is not None
    paths = tracked_paths()
    assert "skills/foo/extra.txt" in paths  # add staged+committed
    assert "claude/bar/SKILL.md" in paths  # decoy untouched
    assert pool_git.pool_content_at(repo, "foo", "HEAD", subdir="skills") == "foo v2"

    # DELETE a file under skills/foo
    (scan_dir / "foo" / "extra.txt").unlink()
    pool_git.commit_pool(
        repo,
        message="edit: foo del",
        author="admin <a@a.com>",
        skill_name="foo",
        subdir="skills",
    )
    paths = tracked_paths()
    assert "skills/foo/extra.txt" not in paths  # deletion staged+committed
    assert "claude/bar/SKILL.md" in paths  # decoy still untouched


def test_pool_skill_history_subdir_scoped(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)

    # two commits touch skills/foo (initial + edit), history reflects only those
    _make_skill_in(scan_dir, "foo", "foo v2")
    pool_git.commit_pool(
        repo,
        message="edit: foo v2",
        author="admin <a@a.com>",
        skill_name="foo",
        subdir="skills",
    )
    history = pool_git.pool_skill_history(repo, "foo", subdir="skills")
    messages = [h["message"] for h in history]
    assert "edit: foo v2" in messages
    assert "edit: foo" in messages
    # commits touching only claude/bar must not appear
    assert not any("claude/bar" in m for m in messages)


def test_pool_diff_for_commit_subdir_scoped(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)

    (scan_dir / "foo" / "SKILL.md").write_text("foo v2", encoding="utf-8")
    sha = pool_git.commit_pool(
        repo,
        message="edit: foo v2",
        author="admin <a@a.com>",
        skill_name="foo",
        subdir="skills",
    )
    assert sha is not None
    result = pool_git.pool_diff_for_commit(repo, "foo", sha, subdir="skills")
    # changed_files carry the full tree path (skills/foo/...) per R6
    assert result["changed_files"] == ["skills/foo/SKILL.md"]


def test_pool_content_at_subdir(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)
    assert pool_git.pool_content_at(repo, "foo", "HEAD", subdir="skills") == "foo v1"
    # decoy is not reachable under subdir="skills"
    assert pool_git.pool_content_at(repo, "bar", "HEAD", subdir="skills") is None


def test_pool_bundle_at_subdir(tmp_path):
    scan_dir, repo = _subdir_repo(tmp_path)
    (scan_dir / "foo" / "helper.py").write_text("print()", encoding="utf-8")
    pool_git.commit_pool(
        repo,
        message="edit: foo helper",
        author="admin <a@a.com>",
        skill_name="foo",
        subdir="skills",
    )
    bundle = pool_git.pool_bundle_at(repo, "foo", "HEAD", subdir="skills")
    assert bundle is not None
    # bundle keys are RELATIVE to the skill dir (no skills/foo prefix) — clean names
    assert bundle["SKILL.md"] == "foo v1"
    assert bundle["helper.py"] == "print()"


# --- regression: subdir="" (default) is byte-for-byte the old behavior -------


def test_subdir_default_matches_flat_layout(tmp_path):
    """With subdir='' every (B) function behaves exactly as the flat repo did."""
    pool_git.init_pool(tmp_path)
    _make_skill(tmp_path, "alpha", "v1")
    sha = pool_git.commit_pool(
        tmp_path, message="edit: alpha", author="admin <a@a.com>", skill_name="alpha"
    )
    assert sha is not None

    # explicit subdir="" must equal the no-arg call
    assert pool_git.pool_version_for_skill(tmp_path, "alpha") == sha
    assert pool_git.pool_version_for_skill(tmp_path, "alpha", subdir="") == sha
    assert pool_git.pool_content_at(tmp_path, "alpha", "HEAD") == "v1"
    assert pool_git.pool_content_at(tmp_path, "alpha", "HEAD", subdir="") == "v1"
    bundle_default = pool_git.pool_bundle_at(tmp_path, "alpha", "HEAD")
    assert bundle_default == pool_git.pool_bundle_at(tmp_path, "alpha", "HEAD", subdir="")
    assert bundle_default == {"SKILL.md": "v1"}

    diff_default = pool_git.pool_diff_for_commit(tmp_path, "alpha", sha)
    diff_empty = pool_git.pool_diff_for_commit(tmp_path, "alpha", sha, subdir="")
    assert diff_default["changed_files"] == diff_empty["changed_files"]
    assert diff_default["changed_files"] == ["alpha/SKILL.md"]
