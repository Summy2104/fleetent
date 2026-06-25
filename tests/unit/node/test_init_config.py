from __future__ import annotations

from io import StringIO
from pathlib import Path
from unittest.mock import patch

from fleetent import __main__ as cli


def _run_cli(*args: str) -> tuple[str, str, int]:
    stdout, stderr = StringIO(), StringIO()
    exit_code = 0
    with (
        patch("sys.argv", ["fleetent", *args]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
    ):
        try:
            cli.main()
        except SystemExit as exc:
            exit_code = int(exc.code or 0)
    return stdout.getvalue(), stderr.getvalue(), exit_code


def _write_node_template(root: Path, content: str = "FLEETENT_NODE_ID=node-example\n") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "node.env.example").write_text(content, encoding="utf-8")


def test_node_init_config_creates_home_env(monkeypatch, tmp_path) -> None:
    template_root = tmp_path / "templates"
    _write_node_template(
        template_root,
        content=(
            "FLEETENT_NODE_PLATFORM_URL=http://127.0.0.1:8765\n"
            "FLEETENT_NODE_ID=node-example\n"
            "FLEETENT_NODE_SERVICE_KEY=\n"
        ),
    )
    home_dir = tmp_path / "home"
    monkeypatch.chdir(template_root)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("node", "init-config")

    assert code == 0
    assert err == ""
    assert "create node/.env" in out
    assert "service key" in out.lower()
    assert (home_dir / "node" / ".env").read_text(encoding="utf-8") == (
        "FLEETENT_NODE_PLATFORM_URL=http://127.0.0.1:8765\n"
        "FLEETENT_NODE_ID=node-example\n"
        "FLEETENT_NODE_SERVICE_KEY=\n"
    )


def test_node_init_config_skips_existing_and_force_overwrites(monkeypatch, tmp_path) -> None:
    template_root = tmp_path / "templates"
    _write_node_template(template_root, content="FLEETENT_NODE_ID=node-from-template\n")
    home_dir = tmp_path / "home"
    node_env = home_dir / "node" / ".env"
    node_env.parent.mkdir(parents=True, exist_ok=True)
    node_env.write_text("FLEETENT_NODE_ID=node-existing\n", encoding="utf-8")
    monkeypatch.chdir(template_root)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("node", "init-config")

    assert code == 0
    assert err == ""
    assert "skip node/.env" in out
    assert node_env.read_text(encoding="utf-8") == "FLEETENT_NODE_ID=node-existing\n"

    out, err, code = _run_cli("node", "init-config", "--force")

    assert code == 0
    assert err == ""
    assert "overwrite node/.env" in out
    assert node_env.read_text(encoding="utf-8") == "FLEETENT_NODE_ID=node-from-template\n"
