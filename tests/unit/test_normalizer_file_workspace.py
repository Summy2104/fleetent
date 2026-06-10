"""File attachments are written into the session sandbox workspace's uploads/."""

from fleetent import paths
from fleetent.im_gateway.normalizer import _safe_filename, _save_file_to_workspace
from fleetent.tools.builtin_tools import _get_manager


def test_safe_filename_strips_path_components():
    assert _safe_filename("../../etc/passwd") == "passwd"
    assert _safe_filename("/abs/path/report.pdf") == "report.pdf"


def test_safe_filename_keeps_extension():
    assert _safe_filename("data.xlsx") == "data.xlsx"


def test_safe_filename_empty_fallback():
    assert _safe_filename("") == "file"
    assert _safe_filename("///") == "file"


def test_safe_filename_strips_control_chars():
    out = _safe_filename("a\nb\t.csv")
    assert "\n" not in out
    assert "\t" not in out
    assert out.endswith(".csv")


def test_save_file_writes_relative_uploads_path(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    rel = _save_file_to_workspace(b"hello", "data.xlsx", "sess1", None)
    assert rel == "uploads/data.xlsx"
    manager = _get_manager()
    root = manager.workspace_host_path(manager.scope, "sess1", "default")
    assert (root / rel).read_bytes() == b"hello"


def test_save_file_no_overwrite_on_collision(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    r1 = _save_file_to_workspace(b"one", "x.csv", "s", None)
    r2 = _save_file_to_workspace(b"two", "x.csv", "s", None)
    assert r1 != r2
    manager = _get_manager()
    root = manager.workspace_host_path(manager.scope, "s", "default")
    assert (root / r1).read_bytes() == b"one"
    assert (root / r2).read_bytes() == b"two"


def test_save_file_malicious_name_stays_in_uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "workspaces_dir", lambda: tmp_path)
    rel = _save_file_to_workspace(b"x", "../../etc/passwd", "s", None)
    assert rel == "uploads/passwd"
    manager = _get_manager()
    root = manager.workspace_host_path(manager.scope, "s", "default")
    f = root / rel
    assert f.read_bytes() == b"x"
    assert f.resolve().parent == (root / "uploads").resolve()
