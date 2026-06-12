"""Unit tests: DockerBackend skills mount flags + SKILLS_DIR env (sandbox-skill-mount).

Pure flag/string assembly — no docker. Asserts `_skill_mount_flags` produces the
ro/rw bind for `/workspace/skills` and that `SKILLS_DIR=/workspace/skills` is injected
into env flags alongside `sandbox_env`.
"""

from __future__ import annotations

from fleetent.integrations.sandbox.backend import SkillMount
from fleetent.integrations.sandbox.backends.docker import DockerBackend


def test_skill_mount_flags_read_only_default() -> None:
    flags = DockerBackend._skill_mount_flags(SkillMount(host_src="/srv/skills"))
    assert flags == ["-v", "/srv/skills:/workspace/skills:ro"]


def test_skill_mount_flags_writable() -> None:
    flags = DockerBackend._skill_mount_flags(SkillMount(host_src="/srv/skills", read_only=False))
    assert flags == ["-v", "/srv/skills:/workspace/skills"]


def test_skill_mount_flags_none_no_mount() -> None:
    assert DockerBackend._skill_mount_flags(None) == []


def test_skills_dir_env_injected_with_skill_mount() -> None:
    # When a skill mount is present, SKILLS_DIR=/workspace/skills enters env flags.
    env = DockerBackend._skills_env(SkillMount(host_src="/srv/skills"))
    assert env == {"SKILLS_DIR": "/workspace/skills"}


def test_skills_dir_env_none_when_no_mount() -> None:
    assert DockerBackend._skills_env(None) == {}


def test_skills_dir_coexists_with_sandbox_env() -> None:
    # The injected SKILLS_DIR must not be dropped when sandbox_env carries other vars,
    # and a sandbox_env SKILLS_DIR must not silently override the platform injection.
    merged = DockerBackend._merge_skills_env(
        {"FOO": "bar", "SKILLS_DIR": "/evil"}, SkillMount(host_src="/srv/skills")
    )
    assert merged["FOO"] == "bar"
    assert merged["SKILLS_DIR"] == "/workspace/skills"
