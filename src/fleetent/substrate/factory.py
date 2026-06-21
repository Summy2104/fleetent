"""Substrate backend factory."""

from __future__ import annotations

from urllib.parse import urlparse

from fleetent.db import SQLiteSubstrateBackend, _sqlite_path
from fleetent.substrate.backend import BaseSubstrateBackend


def create_substrate(database_url: str) -> BaseSubstrateBackend:
    """Return a substrate backend selected by database URL scheme."""
    parsed = urlparse(database_url)
    if parsed.scheme in {"", "sqlite"}:
        if parsed.scheme == "sqlite" and parsed.netloc not in {"", "localhost"}:
            raise ValueError("sqlite database_url must use a local file path")
        path = _sqlite_path(database_url, parsed.path or database_url)
        return SQLiteSubstrateBackend(path=path)
    raise ValueError(f"database backend is not supported yet: {parsed.scheme}")
