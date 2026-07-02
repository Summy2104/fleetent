"""Unit tests for the Bitbucket git platform backend (skill-git-platform).

PR lifecycle goes through Bitbucket Data Center REST (mocked with respx); ``push_branch``
speaks the raw git protocol via dulwich and is exercised against a real local bare repo
(file:// round-trip). ``available`` must probe without raising.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import respx
from dulwich import porcelain

from fleetent.integrations.git_platform import GitPlatformConfig
from fleetent.integrations.git_platform.backends.bitbucket import BitbucketBackend

_BASE = "https://git.example.com"
_PR_PATH = "/rest/api/1.0/projects/PROJ/repos/skills/pull-requests"


def _cfg(remote_url: str) -> GitPlatformConfig:
    return GitPlatformConfig(
        provider="bitbucket",
        remote_url=remote_url,
        branch="main",
        branch_prefix="backflow",
        auto_open_pr=True,
        base_url=_BASE,
        project="PROJ",
        repo="skills",
        username="bot",
        token="secret-token",
    )


def _seed_remote(tmp_path: Path) -> str:
    """Build a bare 'remote' repo with one commit on `main`; return its file:// URL."""
    bare = tmp_path / "remote.git"
    porcelain.init(str(bare), bare=True)
    seed = tmp_path / "seed"
    porcelain.clone(str(bare), str(seed))
    (seed / "README.md").write_text("seed\n")
    porcelain.add(str(seed), paths=[str(seed / "README.md")])
    porcelain.commit(str(seed), message=b"init", author=b"t <t@t>", committer=b"t <t@t>")
    porcelain.push(str(seed), str(bare), "refs/heads/master:refs/heads/main")
    return f"file://{bare}"


def test_push_branch_creates_branch_with_bundle(tmp_path: Path) -> None:
    url = _seed_remote(tmp_path)
    backend = BitbucketBackend(config=_cfg(url))

    sha = backend.push_branch(
        branch="backflow/support-bot/crm-ops",
        bundle={"SKILL.md": "---\nname: crm-ops\n---\nbody\n", "scripts/run.sh": "echo hi\n"},
        subdir="crm-ops",
        base_ref="main",
        message="backflow crm-ops from support-bot",
        author="fleetent <bot@fleetent>",
    )
    assert isinstance(sha, str) and sha

    # Re-clone the remote branch and assert the bundle landed under the subdir.
    check = tmp_path / "check"
    porcelain.clone(url, str(check), branch=b"backflow/support-bot/crm-ops")
    assert (check / "crm-ops" / "SKILL.md").read_text().endswith("body\n")
    assert (check / "crm-ops" / "scripts" / "run.sh").read_text() == "echo hi\n"


@respx.mock
def test_open_get_merge_close_pull_request() -> None:
    backend = BitbucketBackend(config=_cfg("https://git.example.com/scm/PROJ/skills.git"))

    respx.post(f"{_BASE}{_PR_PATH}").mock(
        return_value=httpx.Response(
            201,
            json={
                "id": 42,
                "version": 0,
                "state": "OPEN",
                "fromRef": {"displayId": "backflow/support-bot/crm-ops"},
                "links": {
                    "self": [{"href": f"{_BASE}/projects/PROJ/repos/skills/pull-requests/42"}]
                },
            },
        )
    )
    pr = backend.open_pull_request(
        source_branch="backflow/support-bot/crm-ops", target_branch="main", title="crm-ops"
    )
    assert pr.pr_id == "42"
    assert pr.state == "open"
    assert pr.url.endswith("/pull-requests/42")

    respx.get(f"{_BASE}{_PR_PATH}/42").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "version": 1,
                "state": "OPEN",
                "fromRef": {"displayId": "backflow/support-bot/crm-ops"},
                "links": {"self": [{"href": f"{_BASE}{_PR_PATH}/42"}]},
            },
        )
    )
    got = backend.get_pull_request("42")
    assert got.pr_id == "42" and got.state == "open"

    respx.post(f"{_BASE}{_PR_PATH}/42/merge").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "state": "MERGED",
                "fromRef": {"displayId": "backflow/support-bot/crm-ops"},
                "links": {"self": [{"href": f"{_BASE}{_PR_PATH}/42"}]},
                "properties": {"mergeCommit": {"id": "abcdef1234567890"}},
            },
        )
    )
    merged = backend.merge_pull_request("42")
    assert merged.state == "merged"
    assert merged.merge_commit == "abcdef1234567890"

    respx.post(f"{_BASE}{_PR_PATH}/42/decline").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": 42,
                "state": "DECLINED",
                "fromRef": {"displayId": "backflow/support-bot/crm-ops"},
                "links": {"self": [{"href": f"{_BASE}{_PR_PATH}/42"}]},
            },
        )
    )
    closed = backend.close_pull_request("42")
    assert closed.state == "closed"


def test_available_never_raises_on_unreachable() -> None:
    backend = BitbucketBackend(config=_cfg("https://127.0.0.1:1/scm/PROJ/skills.git"))
    # Probe must return a bool, never raise, even when the host is unreachable.
    assert backend.available() in (True, False)


def test_capabilities_declare_full_pr_support() -> None:
    assert BitbucketBackend.capabilities.open_pr is True
    assert BitbucketBackend.capabilities.merge_pr is True
    assert BitbucketBackend.capabilities.close_pr is True
    assert BitbucketBackend.capabilities.query_pr is True
