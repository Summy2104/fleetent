from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from fleetent import __main__ as cli


def test_kb_worker_init_config_is_no_longer_supported() -> None:
    stdout, stderr = StringIO(), StringIO()
    with (
        patch("sys.argv", ["fleetent", "kb-worker", "init-config"]),
        patch("sys.stdout", stdout),
        patch("sys.stderr", stderr),
        pytest.raises(SystemExit) as exc_info,
    ):
        cli.main()

    assert exc_info.value.code == 2
    assert stdout.getvalue() == ""
    assert "unrecognized arguments: init-config" in stderr.getvalue()
