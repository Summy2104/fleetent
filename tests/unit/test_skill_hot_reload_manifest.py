"""External-file hot-reload: _manifest maintenance + refresh_if_changed (skill-external-hot-reload).

File-based registry behavior; tmp_path isolates the skills root (no DB).
"""

import os
import textwrap

import pytest

import fleetent.skills.registry as sr


@pytest.fixture(autouse=True)
def reset_registry(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "BUILTIN_SKILLS_DIR", tmp_path / "_no_builtin")
    sr._index.clear()
    sr._manifest.clear()
    yield
    sr._index.clear()
    sr._manifest.clear()


def _skill_text(name, body):
    return textwrap.dedent(f"""\
        ---
        name: {name}
        description: A {name} skill for hot-reload tests.
        ---
        {body}
    """)


def _write_skill(root, name, body="body"):
    d = root / name
    d.mkdir(parents=True)
    (d / "SKILL.md").write_text(_skill_text(name, body))


def _write_skill_overwrite(root, name, body):
    (root / name / "SKILL.md").write_text(_skill_text(name, body))


# --- _manifest maintenance (task 1.1/1.2) ---


def test_scan_populates_manifest(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    _write_skill(root, "beta")
    sr.scan(str(root))
    # one manifest entry per SKILL.md, value = (mtime_ns, size)
    assert set(sr._manifest.keys()) == {"alpha/SKILL.md", "beta/SKILL.md"}
    for val in sr._manifest.values():
        assert isinstance(val, tuple) and len(val) == 2
        assert all(isinstance(x, int) for x in val)


def test_reload_refreshes_manifest(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    sr.scan(str(root))
    _write_skill(root, "gamma")
    sr.reload(str(root))
    assert "gamma/SKILL.md" in sr._manifest
    assert "alpha/SKILL.md" in sr._manifest


# --- refresh_if_changed (task 1.3/1.4) ---


def test_refresh_unchanged_returns_false(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    sr.scan(str(root))
    assert sr.refresh_if_changed(str(root)) is False
    assert set(sr._index) == {"alpha"}


def test_refresh_detects_added_skill(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    sr.scan(str(root))
    _write_skill(root, "beta")  # external add
    assert sr.refresh_if_changed(str(root)) is True
    assert "beta" in sr._index


def test_refresh_detects_edit(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha", body="old body")
    sr.scan(str(root))
    _write_skill_overwrite(root, "alpha", "A much longer new body that changes size.")
    assert sr.refresh_if_changed(str(root)) is True
    assert "longer new body" in sr.load("alpha")


def test_refresh_detects_delete(tmp_path):
    root = tmp_path / "skills"
    _write_skill(root, "alpha")
    _write_skill(root, "beta")
    sr.scan(str(root))
    import shutil

    shutil.rmtree(root / "beta")  # external delete
    assert sr.refresh_if_changed(str(root)) is True
    assert "beta" not in sr._index


def test_refresh_no_baseline_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr(sr, "_last_skills_dir", None)
    assert sr.refresh_if_changed(None) is False


def test_refresh_is_metadata_only_not_content(tmp_path):
    """Same-size content swap with mtime restored MUST NOT trigger (proves stat-only)."""
    root = tmp_path / "skills"
    _write_skill(root, "alpha", body="AAAA")
    sr.scan(str(root))
    p = root / "alpha" / "SKILL.md"
    st = p.stat()
    text = p.read_text()
    # swap 'AAAA' -> 'BBBB' (identical length => identical size), then restore mtime_ns
    p.write_text(text.replace("AAAA", "BBBB"))
    os.utime(p, ns=(st.st_atime_ns, st.st_mtime_ns))
    assert sr.refresh_if_changed(str(root)) is False
