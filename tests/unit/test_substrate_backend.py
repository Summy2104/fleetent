from pathlib import Path

import pytest

from fleetent.db import SQLiteSubstrateBackend, create_substrate


def test_create_substrate_uses_sqlite_backend_for_sqlite_url() -> None:
    backend = create_substrate("sqlite:///data/fleetent.db")

    assert isinstance(backend, SQLiteSubstrateBackend)
    assert backend.path == Path("data/fleetent.db")


def test_create_substrate_uses_sqlite_backend_for_local_path() -> None:
    backend = create_substrate("data/fleetent.db")

    assert isinstance(backend, SQLiteSubstrateBackend)
    assert backend.path == Path("data/fleetent.db")


def test_sqlite_substrate_capabilities_are_readable() -> None:
    backend = create_substrate("sqlite:///data/fleetent.db")

    assert backend.capabilities.network is False
    assert backend.capabilities.shared_across_hosts is False
    assert backend.capabilities.embedded_migrations is True


def test_create_substrate_rejects_unknown_scheme() -> None:
    with pytest.raises(ValueError, match="database backend is not supported yet: postgresql"):
        create_substrate("postgresql://fleetent:secret@localhost/fleetent")
