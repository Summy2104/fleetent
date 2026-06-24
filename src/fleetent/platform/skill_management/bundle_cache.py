from __future__ import annotations

import gzip
import hashlib
import io
import os
import tarfile
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CachedSkillBundle:
    skill_name: str
    base_version: str
    bundle_path: Path
    bundle_sha256: str


def _bundle_member_name(skill_dir: Path, path: Path) -> str:
    try:
        relpath = path.relative_to(skill_dir)
    except ValueError as exc:
        raise ValueError(f"unsafe bundle path outside skill root: {path}") from exc
    if relpath.is_absolute() or ".." in relpath.parts:
        raise ValueError(f"unsafe bundle path: {relpath}")
    if any(part == ".git" for part in relpath.parts):
        raise ValueError(f"unsafe bundle path under vcs metadata: {relpath}")
    return f"{skill_dir.name}/{relpath.as_posix()}"


def skill_directory_version(skill_dir: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(_iter_bundle_files(skill_dir)):
        digest.update(_bundle_member_name(skill_dir, path).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def ensure_bundle_cached(
    *,
    pool_dir: Path,
    cache_dir: Path,
    skill_name: str,
    base_version: str,
) -> CachedSkillBundle:
    skill_dir = pool_dir / skill_name
    if not skill_dir.is_dir():
        raise FileNotFoundError(f"skill {skill_name!r} not found in pool")
    cache_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = cache_dir / f"{skill_name}@{base_version}.tar.gz"
    if not bundle_path.exists():
        _write_bundle_atomic(skill_dir=skill_dir, bundle_path=bundle_path)
    return CachedSkillBundle(
        skill_name=skill_name,
        base_version=base_version,
        bundle_path=bundle_path,
        bundle_sha256=_sha256_file(bundle_path),
    )


def _iter_bundle_files(skill_dir: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(skill_dir.rglob("*")):
        if any(part == ".git" for part in path.relative_to(skill_dir).parts):
            continue
        stat = os.lstat(path)
        if os.path.islink(path):
            raise ValueError(f"unsafe symlink in skill bundle: {path}")
        if not path.is_file():
            continue
        if stat.st_nlink > 1:
            raise ValueError(f"unsafe hardlink in skill bundle: {path}")
        files.append(path)
    return files


def _write_bundle_atomic(*, skill_dir: Path, bundle_path: Path) -> None:
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{bundle_path.name}.",
        suffix=".tmp",
        dir=str(bundle_path.parent),
    )
    os.close(fd)
    tmp_path = Path(tmp_name)
    try:
        with tmp_path.open("wb") as raw:
            with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as gz:
                with tarfile.open(fileobj=gz, mode="w") as archive:
                    for path in _iter_bundle_files(skill_dir):
                        data = path.read_bytes()
                        info = tarfile.TarInfo(name=_bundle_member_name(skill_dir, path))
                        info.size = len(data)
                        info.mtime = 0
                        info.mode = 0o644
                        info.uid = 0
                        info.gid = 0
                        archive.addfile(info, io.BytesIO(data))
        tmp_path.replace(bundle_path)
    except Exception:
        tmp_path.unlink(missing_ok=True)
        raise


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()
