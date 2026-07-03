"""Bitbucket Data Center git platform backend (skill-git-platform).

PR lifecycle goes through the Bitbucket DC REST API
(``/rest/api/1.0/projects/{project}/repos/{repo}/pull-requests``) with HTTP basic auth;
``push_branch`` speaks the raw git protocol via dulwich (basic-auth credentials embedded
in the clone/push URL, redacted in logs). All git interaction stays platform-side.
"""

from __future__ import annotations

import shutil
import socket
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlsplit

import httpx
from dulwich import porcelain

from fleetent.integrations.git_platform.backend import (
    BaseGitPlatformBackend,
    GitPlatformCapabilities,
    GitPlatformUnavailableError,
    PullRequestRef,
)
from fleetent.integrations.git_platform.config import GitPlatformConfig

_HTTP_TIMEOUT = 30.0
_PROBE_TIMEOUT = 2.0
# Bitbucket DC PR states -> normalised states.
_STATE_MAP = {"OPEN": "open", "MERGED": "merged", "DECLINED": "closed"}


def _normalise_state(raw: str) -> str:
    return _STATE_MAP.get(raw, raw.lower())


class BitbucketBackend(BaseGitPlatformBackend):
    """Bitbucket Data Center backend: full PR lifecycle + branch push."""

    name = "bitbucket"
    capabilities = GitPlatformCapabilities(
        open_pr=True,
        merge_pr=True,
        close_pr=True,
        query_pr=True,
        server_side_merge=True,
        delete_source_branch=True,
    )

    def __init__(self, *, config: GitPlatformConfig) -> None:
        self.config = config

    # -- raw git (dulwich) --------------------------------------------------

    def _auth_url(self) -> str:
        """Embed basic-auth creds into an http(s) remote URL; pass other schemes through."""
        url = self.config.remote_url
        if self.config.username and self.config.token and url.startswith(("http://", "https://")):
            scheme, rest = url.split("://", 1)
            return f"{scheme}://{quote(self.config.username)}:{quote(self.config.token)}@{rest}"
        return url

    def _redact(self, text: str) -> str:
        if self.config.token:
            return text.replace(self.config.token, "***")
        return text

    def push_branch(
        self,
        *,
        branch: str,
        bundle: dict[str, str],
        subdir: str,
        base_ref: str,
        message: str,
        author: str,
    ) -> str:
        url = self._auth_url()
        with tempfile.TemporaryDirectory() as tmp:
            try:
                # Shallow clone (depth=1): fetch only the base_ref tip, not full history. A
                # full clone of a large monorepo mirror (~100MB) took minutes per proposal;
                # depth=1 pulls just the tip tree (seconds). The new backup commit's parent is
                # the shallow tip — which the remote already has — so the push stays incremental.
                self._shallow_clone(url, tmp, base_ref)
            except GitPlatformUnavailableError:
                raise
            except Exception as exc:  # dulwich raises a wide range on transport failure
                raise GitPlatformUnavailableError(
                    f"clone {self._redact(self.config.remote_url)} failed: {self._redact(str(exc))}"
                ) from exc

            target = Path(tmp) / subdir
            if target.exists():
                shutil.rmtree(target)
            written: list[str] = []
            for rel, content in bundle.items():
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content)
                written.append(str(dest))

            porcelain.add(tmp, paths=written)
            commit_sha = porcelain.commit(
                tmp,
                message=message.encode(),
                author=author.encode(),
                committer=author.encode(),
            )
            try:
                porcelain.branch_create(tmp, branch)
                porcelain.push(tmp, url, f"refs/heads/{branch}:refs/heads/{branch}")
            except Exception as exc:
                raise GitPlatformUnavailableError(
                    f"push {branch} failed: {self._redact(str(exc))}"
                ) from exc
            return commit_sha.decode()

    @staticmethod
    def _shallow_clone(url: str, target: str, base_ref: str) -> None:
        """Clone only ``base_ref``'s tip (depth=1). Falls back to a full clone if the
        transport/dulwich build doesn't support shallow (e.g. some local file:// paths)."""
        try:
            porcelain.clone(url, target, branch=base_ref.encode(), depth=1)
        except TypeError:
            # Older dulwich without a ``depth`` kwarg — fall back to a full clone.
            porcelain.clone(url, target, branch=base_ref.encode())

    # -- reachability -------------------------------------------------------

    def available(self) -> bool:
        """TCP-probe the git remote host; never raises."""
        parts = urlsplit(self.config.remote_url)
        if not parts.hostname:
            # Local (file://) or path-only remotes are always reachable.
            return True
        port = parts.port or (443 if parts.scheme == "https" else 80)
        try:
            with socket.create_connection((parts.hostname, port), timeout=_PROBE_TIMEOUT):
                return True
        except OSError:
            return False

    # -- pull request REST --------------------------------------------------

    def _pr_base(self) -> str:
        return (
            f"{self.config.base_url}/rest/api/1.0/projects/"
            f"{self.config.project}/repos/{self.config.repo}/pull-requests"
        )

    def _client(self) -> httpx.Client:
        auth = None
        if self.config.username and self.config.token:
            auth = (self.config.username, self.config.token)
        return httpx.Client(auth=auth, timeout=_HTTP_TIMEOUT)

    def _ref(self, data: dict[str, Any]) -> PullRequestRef:
        links = data.get("links", {}).get("self", [{}])
        url = links[0].get("href", "") if links else ""
        merge_commit = data.get("properties", {}).get("mergeCommit", {}).get("id")
        return PullRequestRef(
            pr_id=str(data["id"]),
            url=url,
            state=_normalise_state(str(data.get("state", ""))),
            source_branch=data.get("fromRef", {}).get("displayId", ""),
            merge_commit=merge_commit,
        )

    def _request(
        self, method: str, url: str, *, json: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        try:
            with self._client() as client:
                resp = client.request(method, url, json=json)
                resp.raise_for_status()
                return dict(resp.json())
        except httpx.HTTPError as exc:
            raise GitPlatformUnavailableError(
                f"bitbucket {method} {self._redact(url)} failed: {self._redact(str(exc))}"
            ) from exc

    def open_pull_request(
        self, *, source_branch: str, target_branch: str, title: str, description: str = ""
    ) -> PullRequestRef:
        data = self._request(
            "POST",
            self._pr_base(),
            json={
                "title": title,
                "description": description,
                "fromRef": {"id": f"refs/heads/{source_branch}"},
                "toRef": {"id": f"refs/heads/{target_branch}"},
            },
        )
        return self._ref(data)

    def get_pull_request(self, pr_id: str) -> PullRequestRef:
        return self._ref(self._request("GET", f"{self._pr_base()}/{pr_id}"))

    def merge_pull_request(self, pr_id: str) -> PullRequestRef:
        version = self._request("GET", f"{self._pr_base()}/{pr_id}").get("version", 0)
        return self._ref(
            self._request("POST", f"{self._pr_base()}/{pr_id}/merge", json={"version": version})
        )

    def close_pull_request(self, pr_id: str) -> PullRequestRef:
        version = self._request("GET", f"{self._pr_base()}/{pr_id}").get("version", 0)
        return self._ref(
            self._request("POST", f"{self._pr_base()}/{pr_id}/decline", json={"version": version})
        )
