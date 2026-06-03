def _require_non_empty(value: str, name: str) -> None:
    if not value.strip():
        raise ValueError(f"{name} must not be empty")


def memory_namespace(user_id: str) -> str:
    """Return mem:{user_id}."""
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
