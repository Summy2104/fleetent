"""Unit tests for config_hash (sandbox-hardening, task 3)."""

from __future__ import annotations

from fleetent.integrations.sandbox.config import SandboxResources
from fleetent.integrations.sandbox.hardening import config_hash


def _h(image="img", res=None, env=None, ws="/data/workspaces/s"):
    return config_hash(image, res or SandboxResources(), env, ws)


def test_stable() -> None:
    assert _h() == _h()


def test_sensitive_to_image() -> None:
    assert _h(image="a") != _h(image="b")


def test_sensitive_to_workspace() -> None:
    assert _h(ws="/data/workspaces/a") != _h(ws="/data/workspaces/b")


def test_sensitive_to_resources() -> None:
    assert _h(res=SandboxResources(memory=256)) != _h(res=SandboxResources(memory=512))


def test_sensitive_to_env_keys() -> None:
    assert _h(env={"FOO": "1"}) != _h(env={"BAR": "1"})


def test_insensitive_to_env_values() -> None:
    # Only the key set matters — rotating a value must not force a rebuild.
    assert _h(env={"FOO": "1"}) == _h(env={"FOO": "2"})


def test_short_hex() -> None:
    h = _h()
    assert len(h) == 16
    int(h, 16)
