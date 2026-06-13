from __future__ import annotations

import importlib

import pytest


def test_policy_exports_are_removed_but_budget_api_stays_available() -> None:
    from fleetent import long_term_ctx

    with pytest.raises(ModuleNotFoundError):
        importlib.import_module("fleetent.long_term_ctx." "_policy")

    removed_exports = (
        "AgentContext" "Identity",
        "Context" "Policy",
        "ContextPolicySource" "Budget",
        "ContextPolicy" "Record",
        "resolve_context" "_policy",
        "build_context_with" "_policy",
        "get" "_" "policy",
        "upsert" "_" "policy",
    )
    kept_exports = ("build_context", "BudgetPolicy", "ContextSource", "BuiltContext")

    for name in removed_exports:
        assert not hasattr(long_term_ctx, name)

    for name in kept_exports:
        assert hasattr(long_term_ctx, name)
