"""Tests for VectorFamily enum and family_of() router.

Verifies:
- Known prefixes (mem:/shared:/kb:) map to their families
- Unknown prefix raises (fail-fast)
- Existing helpers (memory_namespace/knowledge_namespace) return values unchanged
"""

from __future__ import annotations

import pytest

from fleetent.vector_store.namespaces import (
    VectorFamily,
    family_of,
    knowledge_namespace,
    memory_namespace,
)


# ── 5.1-a: known prefixes map to correct family ────────────────────────────


def test_family_of_mem_prefix_returns_memory() -> None:
    assert family_of("mem:user-1") == VectorFamily.MEMORY


def test_family_of_mem_with_sub_namespace() -> None:
    assert family_of("mem:user-1:shared") == VectorFamily.MEMORY


def test_family_of_shared_prefix_returns_shared() -> None:
    assert family_of("shared:org:acme") == VectorFamily.SHARED


def test_family_of_kb_prefix_returns_kb() -> None:
    assert family_of("kb:default:global") == VectorFamily.KB


def test_family_of_kb_with_tenant_and_kb() -> None:
    assert family_of("kb:tenant-a:engineering") == VectorFamily.KB


# ── 5.1-b: unknown prefix raises ───────────────────────────────────────────


def test_family_of_unknown_prefix_raises() -> None:
    with pytest.raises(ValueError, match="unknown vector namespace family"):
        family_of("unknown:something")


def test_family_of_empty_string_raises() -> None:
    with pytest.raises(ValueError):
        family_of("")


def test_family_of_no_colon_raises() -> None:
    with pytest.raises(ValueError):
        family_of("justaplainstring")


# ── 5.1-c: existing helpers return values unchanged ────────────────────────


def test_memory_namespace_default() -> None:
    assert memory_namespace("user-1") == "mem:user-1"


def test_memory_namespace_single_param_only() -> None:
    import pytest

    with pytest.raises(TypeError):
        memory_namespace("user-1", "custom")  # type: ignore[call-arg]


def test_knowledge_namespace() -> None:
    assert knowledge_namespace("default", "global") == "kb:default:global"


def test_memory_namespace_empty_user_raises() -> None:
    with pytest.raises(ValueError):
        memory_namespace("")


def test_knowledge_namespace_empty_tenant_raises() -> None:
    with pytest.raises(ValueError):
        knowledge_namespace("", "global")


def test_knowledge_namespace_empty_kb_raises() -> None:
    with pytest.raises(ValueError):
        knowledge_namespace("default", "")
