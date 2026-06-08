"""Shared test fixtures (merged: zhangyang health cache + main migration-based schema)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config

import fleetent.model.provider_health as provider_health
from fleetent import db


def _apply_migrations(db_path: Path) -> None:
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "migrations"))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_path}")
    command.upgrade(cfg, "head")


@pytest.fixture(autouse=True)
def _default_required_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide ANTHROPIC_API_KEY for the default model route across the suite.

    The platform ``Settings`` no longer carries an API key (config consolidation),
    but ``model_router``'s default route still resolves the LLM key from this env
    (CLAUDE.md: "默认路由必需"). Tests with no global env would otherwise fail to
    build a client; set a dummy here. Tests exercising missing-key behaviour can
    monkeypatch.delenv it themselves (autouse runs before the test body).
    """
    if os.environ.get("FLEETENT_EVAL_REAL_LLM") == "1":
        return
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")


@pytest.fixture(autouse=True)
def _isolate_fleetent_home(
    monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory
) -> None:
    """Pin FLEETENT_HOME to a temp dir for every test.

    Without this, the `~/.fleetent` home fallback (configurable-data-home) makes
    any test that resolves config/data/logs outside a repo checkout — e.g. after
    chdir to tmp with no FLEETENT_HOME — write into the real user home. Tests that
    exercise resolution precedence override this via their own monkeypatch.
    """
    monkeypatch.setenv("FLEETENT_HOME", str(tmp_path_factory.mktemp("fleetent_home")))


@pytest.fixture(autouse=True)
def _reset_provider_health_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """Give every test a fresh provider health cache.

    The cache is a process-wide circuit breaker; without a reset a switchable
    failure recorded in one test could leave a model in cooldown for the next,
    making order-dependent tests (e.g. the fallback suite) flaky. A generous
    threshold keeps tests that don't exercise the breaker unaffected.
    """
    monkeypatch.setattr(
        provider_health,
        "_cache",
        provider_health.ProviderHealthCache(failure_threshold=1000, cooldown_seconds=60),
    )


@pytest.fixture(autouse=True)
def _reset_long_term_ctx_knowledge_provider():  # type: ignore[no-untyped-def]
    # long_term_ctx holds the knowledge provider in a module global; tests that
    # set it must not leak it into later tests (ordering-dependent failures).
    yield
    from fleetent.intelligence import long_term_ctx

    long_term_ctx.set_knowledge_provider(None)


@pytest.fixture(autouse=True)
def _reset_agent_config_index():  # type: ignore[no-untyped-def]
    # agent_config publishes the resolved agent index as a module global that
    # runtime config now reads via current()/active_agent(). Tests that publish an
    # index must not leak it into later tests (process-level governance/intelligence
    # resolution would otherwise pick up a stale single agent).
    from fleetent import agent_config

    original = agent_config._index
    yield
    agent_config._index = original


@pytest.fixture(autouse=True)
def _isolate_database_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent DATABASE_URL set by agent_app.boot() from leaking between tests.

    boot() calls _redirect_agent_data_paths() which uses os.environ.setdefault to
    wire the per-agent DB path. Without this fixture the env mutation persists across
    tests, causing ordering-dependent failures in tests that rely on the default value.
    """
    monkeypatch.delenv("DATABASE_URL", raising=False)


@pytest.fixture(autouse=True)
def _isolate_agent_data_redirects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore module-level constants mutated by _redirect_agent_data_paths after each test.

    boot() mutates diagnostics._default_data_dir, session_mgr.SESSIONS_DIR, and
    access.APPROVALS_PATH directly (not via os.environ). Without restoration these
    leak across tests, causing ordering-dependent failures in path-wiring tests.
    """
    from fleetent.im_gateway import access
    from fleetent.observability import diagnostics
    from fleetent.session import manager as session_mgr

    monkeypatch.setattr(session_mgr, "SESSIONS_DIR", session_mgr.SESSIONS_DIR)
    monkeypatch.setattr(access, "APPROVALS_PATH", access.APPROVALS_PATH)
    monkeypatch.setattr(diagnostics, "_default_data_dir", diagnostics._default_data_dir)


@pytest.fixture
def isolated_schedule_db(tmp_path, monkeypatch):  # type: ignore[no-untyped-def]
    db_path = tmp_path / "sched.db"
    database_url = f"sqlite:///{db_path}"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("DATABASE_URL", database_url)
    _apply_migrations(db_path)
    return db.create_database(database_url)
