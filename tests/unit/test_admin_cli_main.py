from __future__ import annotations

import pytest

from fleetent.platform.platform_cli.main import main


def test_main_accepts_argv_param(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc_info:
        main(argv=["--help"])

    assert exc_info.value.code == 0
    assert "usage:" in capsys.readouterr().out


def test_help_prog_is_fleetent_platform(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit):
        main(argv=["--help"])

    assert "usage: fleetent platform" in capsys.readouterr().out
