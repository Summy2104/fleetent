"""Unit: effective-root resolution + /exchange namespace attribution truth table.

Pure path/attribution logic; the ledger lookup (`_find_by_path`) is monkeypatched so
no real DB is touched. Effective roots and on-disk files use tmp_path.
"""

from __future__ import annotations

import pytest

from fleetent import artifact_exchange
from fleetent.artifact_exchange import Artifact, ExchangeResolutionError
from fleetent.integrations.mcp.client import McpServerConfig

# ── effective_root ───────────────────────────────────────────────────────────


def test_effective_root_convention_when_unconfigured(tmp_path):
    server = McpServerConfig(id="google-drive", transport="stdio")
    root = artifact_exchange.effective_root(server, tmp_path)
    assert root == tmp_path / "exchange" / "google-drive" / "data"


def test_effective_root_adopts_explicit_xdg(tmp_path):
    server = McpServerConfig(
        id="gw", transport="stdio", env={"XDG_DATA_HOME": str(tmp_path / "xdg" / "share")}
    )
    root = artifact_exchange.effective_root(server, tmp_path)
    assert root == tmp_path / "xdg" / "share"


def test_effective_root_file_root_takes_precedence(tmp_path):
    server = McpServerConfig(
        id="gw",
        transport="stdio",
        file_root=str(tmp_path / "explicit"),
        env={"XDG_DATA_HOME": str(tmp_path / "xdg")},
    )
    root = artifact_exchange.effective_root(server, tmp_path)
    assert root == tmp_path / "explicit"


# ── resolve truth table ────────────────────────────────────────────────────────


@pytest.fixture
def _exchange(tmp_path, monkeypatch):
    root = tmp_path / "exchange" / "gd" / "data"
    root.mkdir(parents=True)
    (root / "a.txt").write_text("hi")
    artifact_exchange.register_server_root("gd", root)
    monkeypatch.setattr(
        artifact_exchange,
        "_server_roots",
        {"gd": root},
    )

    ledger: dict[tuple[str, str], Artifact] = {}

    def fake_find(server_id, rel_path):
        return ledger.get((server_id, rel_path))

    monkeypatch.setattr(artifact_exchange, "_find_by_path", fake_find)
    return root, ledger


def _art(session_id: str, rel: str = "a.txt") -> Artifact:
    return Artifact("id1", "gd", rel, session_id, "U", rel, None, None, None)


def test_resolve_legal_same_session(_exchange):
    root, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("S1")
    assert artifact_exchange.resolve("/exchange/gd/a.txt", "S1") == root / "a.txt"


def test_resolve_rejects_non_exchange_path(_exchange):
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/somewhere/else", "S1")


def test_resolve_rejects_dotdot_escape(_exchange):
    _, ledger = _exchange
    ledger[("gd", "../secret")] = _art("S1", "../secret")
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/gd/../secret", "S1")


def test_resolve_rejects_unregistered_server(_exchange):
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/unknown/a.txt", "S1")


def test_resolve_rejects_unregistered_artifact(_exchange):
    # File exists on disk but no ledger entry → no attribution → reject.
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/gd/a.txt", "S1")


def test_resolve_rejects_cross_session(_exchange):
    _, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("S2")  # owned by another session
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/gd/a.txt", "S1")


def test_resolve_approved_bypasses_attribution(_exchange):
    root, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("S2")
    assert artifact_exchange.resolve("/exchange/gd/a.txt", "S1", approved=True) == root / "a.txt"


def test_resolve_missing_file_reports_gone(_exchange):
    root, ledger = _exchange
    ledger[("gd", "deleted.txt")] = _art("S1", "deleted.txt")
    with pytest.raises(ExchangeResolutionError, match="不存在|gone|exist"):
        artifact_exchange.resolve("/exchange/gd/deleted.txt", "S1")
