from __future__ import annotations

from pathlib import Path


def test_project_guidance_documents_test_layer_guard_and_unit_boundaries():
    guidance = Path("AGENTS.md").read_text(encoding="utf-8")
    claude_guidance = Path("CLAUDE.md").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "scripts/check_test_layers.py" in guidance
    assert "FastAPI `TestClient`" in guidance
    assert "Alembic migration" in guidance
    assert "`tests.integration.*`" in guidance
    assert "`tmp_path`" in guidance
    # CLAUDE.md is an @AGENTS.md include pointer; guidance content lives in AGENTS.md.
    assert "@AGENTS.md" in claude_guidance
    assert "`sqlite3`" in guidance
    assert "`DB_PATH`" in guidance
    assert "`_init_db()`" in guidance
    assert "`DATABASE_URL=sqlite:///...`" in guidance
    assert "真实 DB file、schema、CRUD 或 store/runtime 协作" in guidance
    assert "只读 legacy shim / public API / path constant" in guidance
    assert "scripts/check_test_layers.py" in makefile
    assert "DB-backed unit tests" in makefile


def test_unit_ci_coverage_gate_keeps_required_scope_and_threshold():
    makefile = Path("Makefile").read_text(encoding="utf-8")
    pipelines = Path("bitbucket-pipelines.yml").read_text(encoding="utf-8")
    guidance = Path("AGENTS.md").read_text(encoding="utf-8")

    assert "uv run coverage run --source=src/fleetent -m pytest tests/unit" in makefile
    assert "uv run coverage report --fail-under=76" in makefile
    assert "uv run coverage run --source=src/fleetent -m pytest tests/unit tests/integration" in (
        makefile
    )
    assert "uv run coverage report --fail-under=88" in makefile
    assert "make test-coverage-ci" in pipelines
    assert "push 路径仅看 unit" in guidance
    assert "每日定时路径看合并覆盖" in guidance
