"""Regression: backflow bundle capture must dial the node's reported forward_host.

The owning-node bundle fetch used to address the node via the bare
``{node_id}.internal`` convention, ignoring the ``forward_host`` the node reported
(e.g. ``127.0.0.1`` on a colocated single-host deployment). On any deployment where
``{node_id}.internal`` does not resolve, the fetch raised, the exception was swallowed
by the status handler, and no backflow proposal was ever created. Capture must reuse
the same forward_host-aware addressing as the live platform→node dial.
"""

from __future__ import annotations

import io
import tarfile
from types import SimpleNamespace

import httpx
import respx

from fleetent.platform.node_management import node_store, placement_store
from fleetent.platform.skill_management import backflow_store


def _bundle_bytes(skill_name: str, files: dict[str, str]) -> bytes:
    payload = io.BytesIO()
    with tarfile.open(fileobj=payload, mode="w:gz") as archive:
        for relpath, text in files.items():
            data = text.encode("utf-8")
            info = tarfile.TarInfo(f"{skill_name}/{relpath}")
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    return payload.getvalue()


@respx.mock
def test_capture_dials_reported_forward_host(monkeypatch) -> None:
    skill = "crm-ops"
    monkeypatch.setattr(
        backflow_store.agent_store,
        "get_by_id",
        lambda _aid: SimpleNamespace(id=7, name="support", tenant_id="acme"),
    )
    monkeypatch.setattr(placement_store, "get_for_agent", lambda _aid: {"node_id": "node-a"})
    monkeypatch.setattr(node_store, "get_node_service_key", lambda _nid: "svc-key")
    monkeypatch.setattr(node_store, "get_forward_host", lambda _nid: "127.0.0.1")
    monkeypatch.delenv("FLEETENT_FORWARDER_HOST_OVERRIDE", raising=False)

    reported = respx.get(
        f"http://127.0.0.1:8767/forward/agents/support/skills/{skill}/bundle"
    ).mock(
        return_value=httpx.Response(
            200, content=_bundle_bytes(skill, {"SKILL.md": "evolved by agent\n"})
        )
    )
    # The unresolvable convention host must NOT be dialed.
    convention = respx.get(
        f"http://node-a.internal:8767/forward/agents/support/skills/{skill}/bundle"
    ).mock(return_value=httpx.Response(500))

    bundle = backflow_store._capture_bundle_from_owning_node(agent_id=7, skill_name=skill)

    assert reported.called
    assert not convention.called
    assert bundle == {"SKILL.md": "evolved by agent\n"}
