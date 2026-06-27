from __future__ import annotations

import gzip
import hashlib
import io
import json
import tarfile

import httpx
import respx

from fleetent.node.config import NodeConfig


def _config(tmp_path) -> NodeConfig:
    return NodeConfig(
        platform_url="https://platform.internal",
        node_id="node-a",
        service_key="ma-" + "1" * 64,
        home_dir=tmp_path,
        interval_seconds=10,
    )


def _bundle_bytes(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with (
        gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz,
        tarfile.open(fileobj=gz, mode="w") as archive,
    ):
        for path, content in sorted(files.items()):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(path)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o644
            archive.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def _manifest(bundle_bytes: bytes, *, base_version: str = "abc123", base_commit: str = "def456"):
    return {
        "name": "incident-review",
        "base_version": base_version,
        "base_commit": base_commit,
        "bundle_url": f"/nodes/node-a/skills/incident-review/bundles/{base_version}.tar.gz",
        "bundle_sha256": hashlib.sha256(bundle_bytes).hexdigest(),
    }


@respx.mock
def test_deployer_downloads_missing_skill_and_records_metadata(tmp_path) -> None:
    from fleetent.node.skill_deployer import NodeSkillDeployer

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    bundle_bytes = _bundle_bytes(
        {
            "incident-review/SKILL.md": (
                "---\nname: incident-review\ndescription: Review incidents\n---\nbody\n"
            ),
            "incident-review/scripts/helper.py": "print('ok')\n",
        }
    )
    manifest = _manifest(bundle_bytes)
    route = respx.get(
        "https://platform.internal/nodes/node-a/skills/incident-review/bundles/abc123.tar.gz"
    ).mock(return_value=httpx.Response(200, content=bundle_bytes))

    NodeSkillDeployer(_config(tmp_path)).sync(home, [manifest])

    assert route.called
    assert (home / "skills" / "incident-review" / "SKILL.md").is_file()
    metadata = json.loads(
        (home / "skills" / "incident-review" / ".fleetent-skill.json").read_text(encoding="utf-8")
    )
    assert metadata["base_version"] == "abc123"
    assert metadata["base_commit"] == "def456"
    assert metadata["home_hash"]


@respx.mock
def test_deployer_skips_matching_local_version_without_download(tmp_path) -> None:
    from fleetent.node.skill_deployer import NodeSkillDeployer

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    bundle_bytes = _bundle_bytes(
        {"incident-review/SKILL.md": "---\nname: incident-review\ndescription: d\n---\nbody\n"}
    )
    manifest = _manifest(bundle_bytes)
    route = respx.get(
        "https://platform.internal/nodes/node-a/skills/incident-review/bundles/abc123.tar.gz"
    ).mock(return_value=httpx.Response(200, content=bundle_bytes))

    deployer = NodeSkillDeployer(_config(tmp_path))
    deployer.sync(home, [manifest])
    deployer.sync(home, [manifest])

    assert len(route.calls) == 1


@respx.mock
def test_deployer_does_not_overwrite_drifted_skill(tmp_path) -> None:
    from fleetent.node.skill_deployer import NodeSkillDeployer

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    bundle_v1 = _bundle_bytes(
        {"incident-review/SKILL.md": "---\nname: incident-review\ndescription: d\n---\nv1\n"}
    )
    bundle_v2 = _bundle_bytes(
        {"incident-review/SKILL.md": "---\nname: incident-review\ndescription: d\n---\nv2\n"}
    )
    manifest_v1 = _manifest(bundle_v1, base_version="abc123", base_commit="def456")
    manifest_v2 = _manifest(bundle_v2, base_version="xyz789", base_commit="uvw000")
    route_v1 = respx.get(
        "https://platform.internal/nodes/node-a/skills/incident-review/bundles/abc123.tar.gz"
    ).mock(return_value=httpx.Response(200, content=bundle_v1))
    route_v2 = respx.get(
        "https://platform.internal/nodes/node-a/skills/incident-review/bundles/xyz789.tar.gz"
    ).mock(return_value=httpx.Response(200, content=bundle_v2))

    deployer = NodeSkillDeployer(_config(tmp_path))
    deployer.sync(home, [manifest_v1])
    (home / "skills" / "incident-review" / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: d\n---\nlocal-drift\n",
        encoding="utf-8",
    )

    deployer.sync(home, [manifest_v2])

    assert route_v1.called
    assert not route_v2.called
    assert "local-drift" in (home / "skills" / "incident-review" / "SKILL.md").read_text(
        encoding="utf-8"
    )


def test_deployer_observe_compares_against_deploy_home_hash_not_base_version(tmp_path) -> None:
    # Regression: drift is "home copy changed since deploy", so it must compare the
    # current content hash against the deploy-time home_hash recorded in metadata —
    # NOT against base_version, which the platform computes with a different algorithm
    # (bundle-member naming) and so never equals _skill_home_hash even for identical
    # content. Comparing against base_version flags every node-managed skill as drifted.
    from fleetent.node.skill_deployer import NodeSkillDeployer, _skill_home_hash

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    skill_dir = home / "skills" / "incident-review"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: d\n---\npristine\n", encoding="utf-8"
    )
    deployed_hash = _skill_home_hash(skill_dir)
    assert deployed_hash is not None
    (skill_dir / ".fleetent-skill.json").write_text(
        json.dumps(
            {
                "base_version": "platform-algo-hash",
                "base_commit": "def456",
                "home_hash": deployed_hash,
            }
        ),
        encoding="utf-8",
    )

    manifest = {
        "name": "incident-review",
        "base_version": "platform-algo-hash",
        "base_commit": "def456",
        "bundle_url": "/nodes/node-a/skills/incident-review/bundles/x.tar.gz",
        "bundle_sha256": "0" * 64,
    }
    deployer = NodeSkillDeployer(_config(tmp_path))

    # Unedited: content matches deploy-time home_hash, so no drift despite base_version mismatch.
    assert deployer.observe(home, [manifest]) == [
        {
            "skill_name": "incident-review",
            "base_version": "platform-algo-hash",
            "base_commit": "def456",
            "drift": False,
        }
    ]

    # Edited locally: content now differs from the deploy-time home_hash → drift.
    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: d\n---\nedited\n", encoding="utf-8"
    )
    assert deployer.observe(home, [manifest])[0]["drift"] is True


def test_deployer_observe_marks_hash_drift_and_runtime_provenance(tmp_path) -> None:
    from fleetent.node.skill_deployer import NodeSkillDeployer

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    skill_dir = home / "skills" / "incident-review"
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        "---\nname: incident-review\ndescription: d\nproposal_id: pr-1\n---\nlocal\n",
        encoding="utf-8",
    )
    (skill_dir / ".fleetent-skill.json").write_text(
        json.dumps(
            {
                "base_version": "abc123",
                "base_commit": "def456",
                "home_hash": "abc123",
            }
        ),
        encoding="utf-8",
    )

    observed = NodeSkillDeployer(_config(tmp_path)).observe(
        home,
        [
            {
                "name": "incident-review",
                "base_version": "abc123",
                "base_commit": "def456",
                "bundle_url": "/nodes/node-a/skills/incident-review/bundles/abc123.tar.gz",
                "bundle_sha256": "0" * 64,
            }
        ],
    )

    assert observed == [
        {
            "skill_name": "incident-review",
            "base_version": "abc123",
            "base_commit": "def456",
            "drift": True,
        }
    ]


@respx.mock
def test_deployer_force_resyncs_drifted_skill_on_epoch_bump(tmp_path) -> None:
    # A backflow decision bumps the manifest's resync_epoch; the node must then
    # force-redeploy the drifted home copy back to the pool head (clearing drift),
    # instead of preserving the local edit forever and re-triggering nomination.
    from fleetent.node.skill_deployer import NodeSkillDeployer

    home = tmp_path / "tenants" / "tenant-1" / "agents" / "support"
    pool_bundle = _bundle_bytes(
        {"incident-review/SKILL.md": "---\nname: incident-review\ndescription: d\n---\npool\n"}
    )
    manifest = _manifest(pool_bundle, base_version="abc123")
    respx.get(
        "https://platform.internal/nodes/node-a/skills/incident-review/bundles/abc123.tar.gz"
    ).mock(return_value=httpx.Response(200, content=pool_bundle))

    deployer = NodeSkillDeployer(_config(tmp_path))
    deployer.sync(home, [manifest])

    skill_md = home / "skills" / "incident-review" / "SKILL.md"
    meta_path = home / "skills" / "incident-review" / ".fleetent-skill.json"

    # Agent edits the home copy → local drift.
    skill_md.write_text(
        "---\nname: incident-review\ndescription: d\n---\nedited by agent\n", encoding="utf-8"
    )

    # No epoch bump → drift is preserved (not overwritten).
    deployer.sync(home, [manifest])
    assert "edited by agent" in skill_md.read_text(encoding="utf-8")

    # Epoch bump → force re-sync back to the pool head; local edit discarded.
    bumped = {**manifest, "resync_epoch": "1"}
    deployer.sync(home, [bumped])
    assert "pool" in skill_md.read_text(encoding="utf-8")
    assert "edited by agent" not in skill_md.read_text(encoding="utf-8")
    assert json.loads(meta_path.read_text(encoding="utf-8"))["resync_epoch"] == "1"

    # Same epoch again → idempotent: no further forced overwrite.
    skill_md.write_text(
        "---\nname: incident-review\ndescription: d\n---\nedited again\n", encoding="utf-8"
    )
    deployer.sync(home, [bumped])
    assert "edited again" in skill_md.read_text(encoding="utf-8")
