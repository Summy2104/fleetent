from __future__ import annotations

import subprocess

from scripts import dev_node_provision


def test_dev_node_provision_defaults_to_platform_port_8765(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(dev_node_provision, "_home_dir", lambda: tmp_path)
    monkeypatch.delenv("NODE_PLATFORM_URL", raising=False)

    def fake_run_admin(*args: str) -> subprocess.CompletedProcess[str]:
        assert args == ("register", "local-node", "--name", "Local Dev Node")
        return subprocess.CompletedProcess(
            args=list(args),
            returncode=0,
            stdout="service_key: ma-1234abcd\n",
            stderr="",
        )

    monkeypatch.setattr(dev_node_provision, "_run_admin", fake_run_admin)

    dev_node_provision.main([])

    env_text = (tmp_path / "node" / ".env").read_text(encoding="utf-8")
    assert "FLEETENT_NODE_PLATFORM_URL=http://127.0.0.1:8765\n" in env_text
