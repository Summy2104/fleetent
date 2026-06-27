from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import tempfile
from pathlib import Path

import httpx

from fleetent.node.config import NodeConfig
from fleetent.skills import registry as skill_registry

_METADATA_FILE = ".fleetent-skill.json"


class NodeSkillDeployer:
    def __init__(self, config: NodeConfig) -> None:
        self._config = config

    def sync(self, agent_home: Path, manifests: list[dict[str, str]]) -> None:
        skills_root = agent_home / "skills"
        skills_root.mkdir(parents=True, exist_ok=True)
        for manifest in manifests:
            self._sync_one(skills_root, manifest)

    def observe(
        self, agent_home: Path, manifests: list[dict[str, str]]
    ) -> list[dict[str, str | bool]]:
        skills_root = agent_home / "skills"
        observed: list[dict[str, str | bool]] = []
        for manifest in manifests:
            skill_name = manifest["name"]
            skill_dir = skills_root / skill_name
            current_hash = _skill_home_hash(skill_dir)
            metadata = _read_metadata(skill_dir)
            deployed_hash = metadata.get("home_hash") if metadata is not None else None
            # Drift = the home copy changed since we deployed it. Compare against the
            # deploy-time home_hash (same _skill_home_hash algorithm), never against
            # base_version: the platform derives base_version with a different
            # (bundle-member) algorithm, so it never equals current_hash even for
            # identical content and would flag every node-managed skill as drifted.
            drift = bool(
                current_hash is not None
                and (
                    (deployed_hash is not None and current_hash != deployed_hash)
                    or _has_runtime_provenance(skill_dir)
                )
            )
            observed.append(
                {
                    "skill_name": skill_name,
                    "base_version": manifest["base_version"],
                    "base_commit": manifest["base_commit"],
                    "drift": drift,
                }
            )
        return observed

    def _sync_one(self, skills_root: Path, manifest: dict[str, str]) -> None:
        skill_name = manifest["name"]
        desired_version = manifest["base_version"]
        desired_epoch = int(manifest.get("resync_epoch") or 0)
        skill_dir = skills_root / skill_name
        metadata = _read_metadata(skill_dir)
        current_hash = _skill_home_hash(skill_dir)
        local_epoch = int(metadata.get("resync_epoch") or 0) if metadata is not None else 0

        # A bumped resync_epoch (set by the platform after a backflow accept/reject/fork)
        # forces a redeploy that overrides local drift — the decision has resolved it, so
        # the home copy must return to the pool head instead of staying drifted forever.
        force = desired_epoch > local_epoch
        if not force:
            if metadata is not None and metadata.get("home_hash") != current_hash:
                return
            if metadata is not None and metadata.get("base_version") == desired_version:
                return

        bundle_bytes = self._download_bundle(manifest)
        extracted_skill_dir = _extract_bundle(bundle_bytes, skill_name)
        try:
            deployed_hash = _skill_home_hash(extracted_skill_dir)
            _write_skill_atomic(skill_dir, extracted_skill_dir)
            _write_metadata(
                skill_dir,
                {
                    "base_version": desired_version,
                    "base_commit": manifest["base_commit"],
                    "home_hash": deployed_hash,
                    "resync_epoch": str(desired_epoch),
                },
            )
        finally:
            shutil.rmtree(extracted_skill_dir.parent, ignore_errors=True)

    def _download_bundle(self, manifest: dict[str, str]) -> bytes:
        bundle_url = manifest["bundle_url"]
        if bundle_url.startswith("http://") or bundle_url.startswith("https://"):
            url = bundle_url
        else:
            url = f"{self._config.platform_url}{bundle_url}"
        response = httpx.get(
            url,
            headers={"Authorization": f"Bearer {self._config.service_key}"},
            timeout=10.0,
        )
        response.raise_for_status()
        payload = response.content
        digest = hashlib.sha256(payload).hexdigest()
        if digest != manifest["bundle_sha256"]:
            raise ValueError(f"bundle sha256 mismatch for {manifest['name']}")
        return payload


def _extract_bundle(bundle_bytes: bytes, skill_name: str) -> Path:
    temp_root = Path(tempfile.mkdtemp(prefix=f"fleetent-skill-{skill_name}-"))
    with tarfile.open(fileobj=io.BytesIO(bundle_bytes), mode="r:gz") as archive:
        for member in archive.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"unsafe bundle member path: {member.name}")
            if any(part == ".git" for part in member_path.parts):
                raise ValueError(f"unsafe bundle member path: {member.name}")
            if member.issym() or member.islnk():
                raise ValueError(f"unsafe bundle link member: {member.name}")
            if member.isdir():
                continue
            parts = member_path.parts
            if not parts or parts[0] != skill_name:
                raise ValueError(f"unexpected bundle root: {member.name}")
            destination = temp_root.joinpath(*parts)
            destination.parent.mkdir(parents=True, exist_ok=True)
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"unable to extract bundle member: {member.name}")
            destination.write_bytes(extracted.read())
    return temp_root / skill_name


def _write_skill_atomic(dest_skill_dir: Path, extracted_skill_dir: Path) -> None:
    dest_skill_dir.parent.mkdir(parents=True, exist_ok=True)
    staging = dest_skill_dir.parent / f".{dest_skill_dir.name}.staging"
    if staging.exists():
        shutil.rmtree(staging)
    shutil.move(str(extracted_skill_dir), staging)
    if dest_skill_dir.exists():
        shutil.rmtree(dest_skill_dir)
    staging.replace(dest_skill_dir)


def _read_metadata(skill_dir: Path) -> dict[str, str] | None:
    path = skill_dir / _METADATA_FILE
    if not path.exists():
        return None
    return dict(json.loads(path.read_text(encoding="utf-8")))


def _write_metadata(skill_dir: Path, metadata: dict[str, str]) -> None:
    (skill_dir / _METADATA_FILE).write_text(
        json.dumps(metadata, sort_keys=True),
        encoding="utf-8",
    )


def _skill_home_hash(skill_dir: Path) -> str | None:
    if not skill_dir.is_dir():
        return None
    digest = hashlib.sha256()
    found = False
    for path in sorted(skill_dir.rglob("*")):
        if not path.is_file():
            continue
        relpath = path.relative_to(skill_dir)
        if relpath.name == _METADATA_FILE or any(part == ".git" for part in relpath.parts):
            continue
        found = True
        digest.update(relpath.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    if not found:
        return None
    return digest.hexdigest()


def _has_runtime_provenance(skill_dir: Path) -> bool:
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.is_file():
        return False
    frontmatter = skill_registry._parse_frontmatter(skill_md.read_text(encoding="utf-8")) or {}
    return bool(frontmatter.get("proposal_id") or frontmatter.get("applied_at"))


def bundle_skill_directory(skill_dir: Path) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for path in sorted(skill_dir.rglob("*")):
            if not path.is_file():
                continue
            relpath = path.relative_to(skill_dir)
            if relpath.name == _METADATA_FILE or any(part == ".git" for part in relpath.parts):
                continue
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{skill_dir.name}/{relpath.as_posix()}")
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return payload.getvalue()
