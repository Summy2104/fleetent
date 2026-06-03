import fleetent.server as server


def test_admin_login_url_parses_port(monkeypatch):
    monkeypatch.setattr(server.sys, "argv", ["uvicorn", "fleetent.server:app", "--port", "8765"])
    assert server._admin_login_url("/admin") == "http://127.0.0.1:8765/admin/ui"


def test_admin_login_url_default_port(monkeypatch):
    monkeypatch.setattr(server.sys, "argv", ["uvicorn", "fleetent.server:app"])
    assert server._admin_login_url("/admin") == "http://127.0.0.1:8000/admin/ui"


def test_admin_login_url_equals_form_and_host(monkeypatch):
    monkeypatch.setattr(server.sys, "argv", ["uvicorn", "--host=0.0.0.0", "--port=9000"])
    # 0.0.0.0 is remapped to a reachable loopback host for display
    assert server._admin_login_url("/admin") == "http://127.0.0.1:9000/admin/ui"


def test_admin_login_url_custom_host(monkeypatch):
    monkeypatch.setattr(server.sys, "argv", ["uvicorn", "--host", "192.168.1.5", "--port", "80"])
    assert server._admin_login_url("/admin") == "http://192.168.1.5:80/admin/ui"
