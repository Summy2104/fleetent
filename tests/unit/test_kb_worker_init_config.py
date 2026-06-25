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


def _write_template(root: Path, content: str = "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=\n") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "kb-worker.env.example").write_text(content, encoding="utf-8")


def test_kb_worker_init_config_creates_home_env(monkeypatch, tmp_path) -> None:
    template_root = tmp_path / "templates"
    _write_template(
        template_root,
        content=(
            "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///queue.db\n"
            "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL=sqlite:///substrate.db\n"
        ),
    )
    home_dir = tmp_path / "home"
    monkeypatch.chdir(template_root)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb-worker", "init-config")

    assert code == 0
    assert err == ""
    assert "create kb-worker/.env" in out
    assert (home_dir / "kb-worker" / ".env").read_text(encoding="utf-8") == (
        "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///queue.db\n"
        "FLEETENT_KB_WORKER_SUBSTRATE_DATABASE_URL=sqlite:///substrate.db\n"
    )


def test_kb_worker_init_config_skips_existing_and_force_overwrites(monkeypatch, tmp_path) -> None:
    template_root = tmp_path / "templates"
    _write_template(
        template_root,
        content="FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///from-template.db\n",
    )
    home_dir = tmp_path / "home"
    env_path = home_dir / "kb-worker" / ".env"
    env_path.parent.mkdir(parents=True, exist_ok=True)
    env_path.write_text(
        "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///existing.db\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(template_root)
    monkeypatch.setenv("FLEETENT_HOME", str(home_dir))

    out, err, code = _run_cli("kb-worker", "init-config")

    assert code == 0
    assert err == ""
    assert "skip kb-worker/.env" in out
    assert env_path.read_text(encoding="utf-8") == (
        "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///existing.db\n"
    )

    out, err, code = _run_cli("kb-worker", "init-config", "--force")

    assert code == 0
    assert err == ""
    assert "overwrite kb-worker/.env" in out
    assert env_path.read_text(encoding="utf-8") == (
        "FLEETENT_KB_WORKER_QUEUE_DATABASE_URL=sqlite:///from-template.db\n"
    )
