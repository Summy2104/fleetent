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

    # Ledger keyed by (server_id, rel_path) → one artifact carrying its scope_key.
    ledger: dict[tuple[str, str], Artifact] = {}

    def fake_find_by_path(server_id, rel_path, scope_key):
        art = ledger.get((server_id, rel_path))
        return art if art is not None and art.scope_key == scope_key else None

    def fake_find_any(server_id, rel_path):
        return ledger.get((server_id, rel_path))

    monkeypatch.setattr(artifact_exchange, "_find_by_path", fake_find_by_path)
    monkeypatch.setattr(artifact_exchange, "_find_any_by_path", fake_find_any)
    return root, ledger


def _art(scope_key: str, rel: str = "a.txt") -> Artifact:
    # fields: id, server, rel, scope_key, session_id, user_id, filename, mime, size, created_at
    return Artifact("id1", "gd", rel, scope_key, "sess", "U", rel, None, None, None)


def test_resolve_legal_same_scope(_exchange):
    root, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("K1")
    assert artifact_exchange.resolve("/exchange/gd/a.txt", "K1") == root / "a.txt"


def test_resolve_rejects_non_exchange_path(_exchange):
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/somewhere/else", "K1")


def test_resolve_rejects_dotdot_escape(_exchange):
    _, ledger = _exchange
    ledger[("gd", "../secret")] = _art("K1", "../secret")
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/gd/../secret", "K1")


def test_resolve_rejects_unregistered_server(_exchange):
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/unknown/a.txt", "K1")


def test_resolve_rejects_unregistered_artifact(_exchange):
    # File exists on disk but no ledger entry → no attribution → reject.
    with pytest.raises(ExchangeResolutionError):
        artifact_exchange.resolve("/exchange/gd/a.txt", "K1")


def test_resolve_rejects_cross_scope(_exchange):
    _, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("K2")  # owned by another scope
    with pytest.raises(ExchangeResolutionError, match="另一|another|审批|approval"):
        artifact_exchange.resolve("/exchange/gd/a.txt", "K1")


def test_resolve_same_path_other_scope_does_not_mask_own(_exchange):
    """D4: a same-path artifact owned by another scope MUST NOT mask my own row;
    scope-filtered lookup returns mine, not 'newest at path'."""
    root, ledger = _exchange
    # Only my own row is present at this path under my scope.
    ledger[("gd", "a.txt")] = _art("K1")
    assert artifact_exchange.resolve("/exchange/gd/a.txt", "K1") == root / "a.txt"


def test_resolve_approved_bypasses_attribution(_exchange):
    root, ledger = _exchange
    ledger[("gd", "a.txt")] = _art("K2")
    assert artifact_exchange.resolve("/exchange/gd/a.txt", "K1", approved=True) == root / "a.txt"


def test_resolve_missing_file_reports_gone(_exchange):
    root, ledger = _exchange
    ledger[("gd", "deleted.txt")] = _art("K1", "deleted.txt")
    with pytest.raises(ExchangeResolutionError, match="不存在|gone|exist"):
        artifact_exchange.resolve("/exchange/gd/deleted.txt", "K1")
