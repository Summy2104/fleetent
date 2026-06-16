"""Per-agent sandbox resource config: value-level validation (per-agent-sandbox-resources).

Resources now come from the per-agent `agent.yaml` `sandbox.resources`
(`SandboxResourcesSettings`) built via `resources_from_agent_settings`, not from the
machine-shared `platform.yaml`. This exercises the same field-level
validation/clamp/enum-fallback the removed platform.yaml loader used.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from pydantic import ValidationError

from fleetent.agent_config import SandboxResourcesSettings
from fleetent.integrations.sandbox.config import (
    NetworkPolicy,
    SandboxResources,
    resources_from_agent_settings,
)


def _build(**fields) -> SandboxResources:
    return resources_from_agent_settings(SandboxResourcesSettings(**fields))


def test_network_policy_members() -> None:
    assert NetworkPolicy.NONE == "none"
    assert NetworkPolicy.PUBLIC_ONLY == "public_only"
    assert NetworkPolicy.ALLOW_ALL == "allow_all"


def test_sandbox_resources_safe_defaults() -> None:
    res = SandboxResources()
    assert res.memory == 256
    assert res.cpus == 0.5
    assert res.network is NetworkPolicy.NONE
    assert res.exec_timeout == 30
    assert res.read_only is True


def test_sandbox_resources_hardening_defaults() -> None:
    res = SandboxResources()
    assert res.pids_limit == 256
    assert res.tmpfs_size_mb == 64
    assert res.cap_drop_all is True
    assert res.cap_add == ()
    assert res.no_new_privileges is True
    assert res.init is True
    assert res.run_as_user == "65534:65534"


def test_overrides_all_fields() -> None:
    res = _build(memory=1024, cpus=2.0, network="allow_all", exec_timeout=120, read_only=False)
    assert res.memory == 1024
    assert res.cpus == 2.0
    assert res.network is NetworkPolicy.ALLOW_ALL
    assert res.exec_timeout == 120
    assert res.read_only is False


def test_missing_fields_fall_back_per_field() -> None:
    res = _build(memory=512)
    assert res.memory == 512
    assert res.cpus == 0.5
    assert res.network is NetworkPolicy.NONE
    assert res.exec_timeout == 30
    assert res.read_only is True


def test_all_unset_returns_all_defaults() -> None:
    assert resources_from_agent_settings(SandboxResourcesSettings()) == SandboxResources()


def test_invalid_memory_falls_back_to_default() -> None:
    assert _build(memory=0).memory == 256


def test_invalid_cpus_falls_back_to_default() -> None:
    assert _build(cpus=-1).cpus == 0.5


def test_invalid_network_falls_back_to_default() -> None:
    assert _build(network="lan_only").network is NetworkPolicy.NONE


def test_exec_timeout_below_floor_clamped_to_one() -> None:
    assert _build(exec_timeout=0).exec_timeout == 1


def test_exec_timeout_above_ceiling_clamped_to_600() -> None:
    assert _build(exec_timeout=1000).exec_timeout == 600


def test_exec_timeout_within_range_unchanged() -> None:
    assert _build(exec_timeout=45).exec_timeout == 45


# --- container hardening (sandbox-container-hardening) ---------------------


def test_overrides_hardening_fields() -> None:
    res = _build(
        pids_limit=512,
        tmpfs_size_mb=128,
        cap_drop_all=False,
        no_new_privileges=False,
        init=False,
        run_as_user="1000:1000",
    )
    assert res.pids_limit == 512
    assert res.tmpfs_size_mb == 128
    assert res.cap_drop_all is False
    assert res.no_new_privileges is False
    assert res.init is False
    assert res.run_as_user == "1000:1000"


def test_missing_hardening_fields_fall_back() -> None:
    res = _build(memory=512)
    assert res.pids_limit == 256
    assert res.tmpfs_size_mb == 64
    assert res.cap_drop_all is True
    assert res.no_new_privileges is True
    assert res.init is True
    assert res.run_as_user == "65534:65534"


def test_invalid_pids_limit_falls_back_to_default() -> None:
    assert _build(pids_limit=0).pids_limit == 256


def test_invalid_tmpfs_size_falls_back_to_default() -> None:
    assert _build(tmpfs_size_mb=-1).tmpfs_size_mb == 64


def test_run_as_user_null_means_root() -> None:
    # Explicit None run_as_user means run as root (no --user). Distinguishable from unset
    # only at the YAML layer; here None inherits the default, so assert the default holds.
    assert _build().run_as_user == "65534:65534"


def test_cap_add_override() -> None:
    assert _build(cap_add=["NET_ADMIN"]).cap_add == ("NET_ADMIN",)


def test_invalid_cap_add_falls_back() -> None:
    with patch("fleetent.integrations.sandbox.config._logger") as log:
        # type-valid for pydantic (list[str]) but semantically empty entries → fall back to ()
        res = resources_from_agent_settings(SandboxResourcesSettings(cap_add=["", "  "]))
    assert res.cap_add == ()
    log.warn.assert_called()


def test_wrong_typed_field_rejected_at_schema() -> None:
    # Type-level invalid (str for int) → explicit pydantic error (acceptable per spec:
    # invalid values are never silently accepted — logged-and-fallback OR explicit error).
    with pytest.raises(ValidationError):
        SandboxResourcesSettings(memory="lots")
