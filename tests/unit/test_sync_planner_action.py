"""Pure sync-action decision: new vs unchanged vs changed."""

from fleetent.knowledge_base.connectors.state import LocalSourceState
from fleetent.knowledge_base.sync_planner import SyncAction, _action_for_state


def _state(mtime_ns: int, content_hash: str) -> LocalSourceState:
    return LocalSourceState(
        source_id="s",
        tenant_id="t",
        kb_id="kb",
        source_path="/x/a.md",
        mtime_ns=mtime_ns,
        content_hash=content_hash,
        document_id="d",
    )


def test_no_prior_state_is_ingest_new():
    assert _action_for_state(None, 10, "h1") == SyncAction.INGEST_NEW


def test_same_fingerprint_skips_unchanged():
    assert _action_for_state(_state(10, "h1"), 10, "h1") == SyncAction.SKIP_UNCHANGED


def test_changed_mtime_or_hash_reingests():
    assert _action_for_state(_state(10, "h1"), 11, "h1") == SyncAction.REINGEST_CHANGED
    assert _action_for_state(_state(10, "h1"), 10, "h2") == SyncAction.REINGEST_CHANGED
