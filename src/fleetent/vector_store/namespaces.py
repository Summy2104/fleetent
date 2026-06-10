"""Vector namespace helpers and family router.

Namespaces are dot-separated strings like ``mem:user-1`` or ``kb:default:global``.
VectorFamily enumerates the three known prefix groups; family_of() is the single
routing entry point — ad-hoc ``startswith`` checks are banned (§5.6).
"""

from __future__ import annotations

from enum import Enum


class VectorFamily(Enum):
    """Explicit enumeration of the three known vector namespace families."""

    MEMORY = "mem"
    SHARED = "shared"
    KB = "kb"


def family_of(namespace: str) -> VectorFamily:
    """Return the VectorFamily for *namespace*.

    Raises:
        ValueError: The namespace prefix does not match any known family
            (fail-fast: callers must not silently fall through to the wrong backend).
    """
    if not namespace:
        raise ValueError(f"namespace must not be empty, got {namespace!r}")
    prefix = namespace.split(":")[0]
    for family in VectorFamily:
        if family.value == prefix:
            return family
    raise ValueError(
        f"unknown vector namespace family: prefix {prefix!r} in {namespace!r}. "
        f"Known families: {[f.value for f in VectorFamily]}"
    )


def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def memory_namespace(user_id: str) -> str:
    """Return mem:{user_id}.  Agent isolation is physical (per-agent DB), not namespace-based."""
    _require_non_empty(user_id, "user_id")
    return f"mem:{user_id}"


def shared_namespace(scope_type: str, scope_id: str) -> str:
    """Return shared:{scope_type}:{scope_id}."""
    _require_non_empty(scope_type, "scope_type")
    _require_non_empty(scope_id, "scope_id")
    return f"shared:{scope_type}:{scope_id}"


def knowledge_namespace(tenant_id: str, kb_id: str) -> str:
    """Return kb:{tenant_id}:{kb_id}."""
    _require_non_empty(tenant_id, "tenant_id")
    _require_non_empty(kb_id, "kb_id")
    return f"kb:{tenant_id}:{kb_id}"
