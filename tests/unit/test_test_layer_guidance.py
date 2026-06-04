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
    for text in (guidance, claude_guidance):
        assert "`sqlite3`" in text
        assert "`DB_PATH`" in text
        assert "`_init_db()`" in text
        assert "`DATABASE_URL=sqlite:///...`" in text
        assert "真实 DB file、schema、CRUD 或 store/runtime 协作" in text
        assert "只读 legacy shim / public API / path constant" in text
    assert "scripts/check_test_layers.py" in makefile
    assert "DB-backed unit tests" in makefile


def test_unit_ci_coverage_gate_keeps_required_scope_and_threshold():
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "uv run coverage run --source=src/fleetent -m pytest tests/unit" in makefile
    assert "uv run coverage report --fail-under=75" in makefile
