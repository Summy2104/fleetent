from __future__ import annotations

from pathlib import Path


def test_project_guidance_documents_test_layer_guard_and_unit_boundaries():
    guidance = Path("AGENTS.md").read_text(encoding="utf-8")
    makefile = Path("Makefile").read_text(encoding="utf-8")

    assert "scripts/check_test_layers.py" in guidance
    assert "FastAPI `TestClient`" in guidance
    assert "Alembic migration" in guidance
    assert "`tests.integration.*`" in guidance
    assert "`tmp_path`" in guidance
    assert "scripts/check_test_layers.py" in makefile
