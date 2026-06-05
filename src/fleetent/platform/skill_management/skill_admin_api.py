"""FastAPI router for /admin/skills — the Skill management face.

This router owns only the *management* behaviour: listing, the upload/edit gating
pipeline, global + per-agent enablement, archive with reference protection, the
provenance/drift badge, the reflection proposal inbox, and per-skill observation.

The *engine* semantics (matching, injection, security-audit verdicts, hot reload),
the reflection *application* of proposals, and the askit override flow live in their
own domains. They are reached here through small injectable seams (module-level
callables) so this router stays testable in isolation and never imports the agent
loop. Seams whose owning domain is not yet implemented default to documented
placeholders and are monkeypatched in tests.

Auth mirrors user_admin_api: ``Authorization: Session <token>``; reads allow
viewer+admin, writes require admin, high-risk writes require ``X-Confirm: true``.
"""

import io
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile
from pydantic import BaseModel

from fleetent import auth, user_store
from fleetent.governance import audit_log
from fleetent.platform.skill_management import skill_admin_store
from fleetent.skills import registry as skill_registry

router = APIRouter(prefix="/admin/skills")

IDLE_TIMEOUT_SECONDS = 1800
_ADMIN_ROLES = {"admin", "built_in_admin"}


# --- injectable seams (defaults delegate to engine / placeholder follow-ups) ---


def engine_list_skills() -> list[dict[str, str]]:
    """List the engine's current skill index. Defaults to skill_registry."""
    return skill_registry.list_skills()


def engine_skill_content(name: str) -> str | None:
    """Return a skill's raw SKILL.md content. Defaults to skill_registry."""
    try:
        return skill_registry.load(name)
    except Exception:  # noqa: BLE001 — unknown/unreadable skill -> no content
        return None


def engine_skills_dir() -> str:
    """The writable user skills directory (where imports are materialized)."""
    return skill_registry._resolve_skills_dir(None)


def engine_audit(content: str) -> dict[str, Any]:
    """Security-audit a skill body. Owned by the skill domain (follow-up).

    Placeholder default passes everything; tests monkeypatch to exercise the
    suspicious / rejected branches. Returns ``{"verdict", "rules"}``.
    """
    return {"verdict": "pass", "rules": []}


def engine_reload() -> dict[str, Any]:
    """Trigger a hot re-scan of the skills directory. Defaults to skill_registry.scan."""
    try:
        skill_registry.scan()
    except Exception as exc:  # noqa: BLE001 — surface failure to the UI, keep old index
        return {"ok": False, "error": str(exc)}
    return {"ok": True}


def engine_set_global_disabled(skill_name: str, disabled: bool) -> None:
    """Tell the engine the desired global-disabled state. Placeholder (engine reads store)."""
    return None


def engine_observability(skill_name: str) -> dict[str, Any]:
    """Per-skill hit/injection metrics. Owned by observability (follow-up placeholder)."""
    return {"skill_name": skill_name, "hits": 0, "sessions": [], "stale": True}


def _proposal_dict(p: Any) -> dict[str, Any]:
    """Serialize a reflection SkillProposal to a JSON-able review-inbox row."""
    return {
        "id": p.id,
        "type": p.type,
        "target_skill": p.target_skill,
        "reason": p.reason,
        "evidence_refs": list(p.evidence_refs),
        "risk_level": p.risk_level,
        "status": p.status,
        "has_draft": bool(p.suggested_draft),
        "has_diff": bool(p.suggested_diff),
        "created_at": p.created_at.isoformat(),
        "updated_at": p.updated_at.isoformat(),
    }


def reflection_list_proposals() -> list[dict[str, Any]]:
    """Pending Skill proposals from reflection (newest first)."""
    from fleetent.intelligence import reflection

    return [_proposal_dict(p) for p in reflection.list_skill_proposals("pending")]


def reflection_proposal_diff(proposal_id: str) -> dict[str, Any]:
    """Full proposal payload incl. suggested diff/draft, for the review viewer."""
    from fleetent.intelligence import reflection

    try:
        p = reflection.get_skill_proposal(proposal_id)
    except ValueError:
        return {"proposal_id": proposal_id, "diff": "", "draft": ""}
    return {
        **_proposal_dict(p),
        "proposal_id": p.id,
        "diff": p.suggested_diff or "",
        "draft": p.suggested_draft or "",
    }


def reflection_apply_proposal(proposal_id: str, reviewer_user_id: str) -> None:
    """Approve a proposal (status -> approved)."""
    from fleetent.intelligence import reflection

    reflection.approve_skill_proposal(proposal_id, reviewer_user_id=reviewer_user_id)


def reflection_close_proposal(
    proposal_id: str, reviewer_user_id: str, reason: str = "rejected via admin console"
) -> None:
    """Reject a proposal without changing the skill."""
    from fleetent.intelligence import reflection

    reflection.reject_skill_proposal(proposal_id, reviewer_user_id=reviewer_user_id, reason=reason)


def askit_override(skill_name: str, action: str) -> dict[str, Any]:
    """Promote/discard a drifted managed skill via askit. Placeholder (askit follow-up)."""
    return {"skill_name": skill_name, "action": action, "ok": True}


# --- auth helpers -------------------------------------------------------------


def _session_user(authorization: str | None) -> user_store.User:
    if not authorization or not authorization.startswith("Session "):
        raise HTTPException(status_code=401, detail="not authenticated")
    token = authorization.split(" ", 1)[1]
    user_id = auth.validate_session(token, IDLE_TIMEOUT_SECONDS)
    if user_id is None:
        raise HTTPException(status_code=401, detail="invalid or expired session")
    user = user_store.get_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="invalid session")
    return user


def _current_user(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, {"viewer", *_ADMIN_ROLES}):
        raise HTTPException(status_code=403, detail="forbidden")
    return user


def _require_admin(authorization: str | None) -> user_store.User:
    user = _session_user(authorization)
    if not auth.has_role(user, _ADMIN_ROLES):
        raise HTTPException(status_code=403, detail="admin required")
    return user


def _require_confirm(x_confirm: str | None) -> None:
    if x_confirm != "true":
        raise HTTPException(status_code=428, detail="confirmation required for high-risk action")


# --- request bodies -----------------------------------------------------------


class SkillBody(BaseModel):
    name: str
    content: str
    source: str = "adhoc"


class EditBody(BaseModel):
    content: str


class BindingBody(BaseModel):
    enabled: bool


def _validate_frontmatter(content: str) -> bool:
    # zhangyang's _parse_frontmatter returns None for absent/invalid frontmatter
    # (main's returned {}); guard so invalid uploads yield 422 instead of crashing.
    fm = skill_registry._parse_frontmatter(content) or {}
    return bool(fm.get("name")) and bool(fm.get("description"))


def _publish(name: str, content: str, source: str, verdict: dict[str, Any]) -> dict[str, Any]:
    """Apply an audit verdict: quarantine on reject, mark+publish on suspicious, publish on pass."""
    skill_admin_store.set_audit_result(name, verdict["verdict"], verdict.get("rules"))
    if verdict["verdict"] == "rejected":
        skill_admin_store.set_status(name, "quarantined")
        return {
            "name": name,
            "verdict": "rejected",
            "rules": verdict.get("rules", []),
            "published": False,
        }
    skill_admin_store.set_status(name, "active")
    reload_result = engine_reload()
    return {
        "name": name,
        "verdict": verdict["verdict"],
        "rules": verdict.get("rules", []),
        "published": True,
        "reload": reload_result,
    }


# --- list / search ------------------------------------------------------------


@router.get("")
def list_skills(
    authorization: str | None = Header(None),
    q: str | None = None,
    audit_verdict: str | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    _current_user(authorization)
    engine = {s["name"]: s for s in engine_list_skills()}
    rows: list[dict[str, Any]] = []
    names = set(engine) | {s["skill_name"] for s in skill_admin_store.list_states(include_archived)}
    for name in sorted(names):
        state = skill_admin_store.get_state(name)
        if not include_archived and state["status"] == "archived":
            continue
        prov = skill_admin_store.get_provenance(name)
        row = {
            "name": name,
            "description": engine.get(name, {}).get("description", ""),
            "status": state["status"],
            "global_enabled": state["global_enabled"],
            "audit_verdict": state["audit_verdict"],
            "source": prov["source"],
            "drift": prov["drift"],
            "enabling_agents": skill_admin_store.agents_enabling(name),
        }
        if q and q.lower() not in name.lower() and q.lower() not in row["description"].lower():
            continue
        if audit_verdict and row["audit_verdict"] != audit_verdict:
            continue
        rows.append(row)
    return rows


@router.get("/{name}/content")
def skill_content(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    """Raw SKILL.md content for preview / edit prefill."""
    _current_user(authorization)
    content = engine_skill_content(name)
    if content is None:
        raise HTTPException(status_code=404, detail="skill content not found")
    return {"name": name, "content": content}


# --- upload / create / edit ---------------------------------------------------


@router.post("")
def create_skill(body: SkillBody, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    if not _validate_frontmatter(body.content):
        raise HTTPException(
            status_code=422, detail="invalid frontmatter (name/description required)"
        )
    skill_admin_store.set_provenance(body.name, body.source)
    verdict = engine_audit(body.content)
    result = _publish(body.name, body.content, body.source, verdict)
    audit_log.write_audit(user.id, "skill.create", "skill", body.name, detail=result)
    return result


def _safe_skill_name(name: str) -> bool:
    return bool(name) and ".." not in name and all(c.isalnum() or c in "._-" for c in name)


def _import_skill_dir(src_dir: Path, source: str) -> dict[str, Any]:
    """Materialize one skill directory into the skills dir, then publish it.

    Copies the whole directory (SKILL.md plus any supporting files/scripts) so the
    engine's next scan loads it. Raises ValueError for a bad/unsafe skill (caller
    reports it as skipped). The destination skill name comes from the frontmatter.
    """
    skill_file = src_dir / "SKILL.md"
    content = skill_file.read_text(encoding="utf-8")
    fm = skill_registry._parse_frontmatter(content) or {}
    name = str(fm.get("name") or "").strip()
    if not name or not fm.get("description"):
        raise ValueError("invalid frontmatter (name/description required)")
    if not _safe_skill_name(name):
        raise ValueError(f"unsafe skill name: {name!r}")
    dest = Path(engine_skills_dir()) / name
    shutil.copytree(src_dir, dest, dirs_exist_ok=True)
    skill_admin_store.set_provenance(name, source)
    verdict = engine_audit(content)
    return _publish(name, content, source, verdict)


def _run_import(root: Path, recursive: bool, source: str) -> dict[str, Any]:
    """Import one (or, when recursive, every) skill dir under ``root``. Raises HTTP 422
    when nothing importable is found; per-skill failures are collected, not raised."""
    if recursive:
        dirs = sorted(d for d in root.iterdir() if d.is_dir() and (d / "SKILL.md").exists())
        if not dirs:
            raise HTTPException(
                status_code=422, detail="no skill directories (with SKILL.md) found"
            )
    else:
        if not (root / "SKILL.md").exists():
            raise HTTPException(
                status_code=422, detail="no SKILL.md here; use batch for a parent directory"
            )
        dirs = [root]

    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for d in dirs:
        try:
            res = _import_skill_dir(d, source)
            imported.append(
                {"name": res["name"], "verdict": res["verdict"], "published": res["published"]}
            )
        except ValueError as exc:
            skipped.append({"dir": d.name, "reason": str(exc)})
        except Exception as exc:  # noqa: BLE001 — surface copy/IO failure per-skill, keep going
            failed.append({"dir": d.name, "error": str(exc)})
    return {"imported": imported, "skipped": skipped, "failed": failed}


@router.post("/import/upload")
async def import_skills_upload(
    files: list[UploadFile] = File(...),
    source: str = Form("adhoc"),
    authorization: str | None = Header(None),
) -> dict[str, Any]:
    """Import skill(s) from a folder uploaded by the browser (multipart).

    The browser sends each file with its folder-relative path as the filename
    (``<input webkitdirectory>``). The tree is reconstructed in a temp dir and then
    imported. Single-skill vs batch is auto-detected: a SKILL.md at the folder root
    means one skill; otherwise every immediate subdir with a SKILL.md is imported.
    """
    user = _require_admin(authorization)
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        tops: set[str] = set()
        for f in files:
            rel = (f.filename or "").replace("\\", "/").lstrip("/")
            if not rel or ".." in rel.split("/"):
                continue
            data = await f.read()
            # A .zip is the reliable alternative when the OS folder picker is unavailable:
            # extract its tree (zip-slip guarded) instead of storing the archive itself.
            if rel.lower().endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for member in zf.namelist():
                        mrel = member.replace("\\", "/").lstrip("/")
                        if not mrel or mrel.endswith("/") or ".." in mrel.split("/"):
                            continue
                        tops.add(mrel.split("/", 1)[0])
                        mdest = root / mrel
                        mdest.parent.mkdir(parents=True, exist_ok=True)
                        mdest.write_bytes(zf.read(member))
                continue
            tops.add(rel.split("/", 1)[0])
            dest = root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        # webkitdirectory nests everything under the chosen folder; descend into it.
        base = root / next(iter(tops)) if len(tops) == 1 else root
        recursive = not (base / "SKILL.md").exists()
        summary = _run_import(base, recursive, source)
    audit_log.write_audit(user.id, "skill.import", "skill", "upload", detail=summary)
    return summary


@router.put("/{name}")
def edit_skill(
    name: str, body: EditBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    if not _validate_frontmatter(body.content):
        raise HTTPException(
            status_code=422, detail="invalid frontmatter (name/description required)"
        )
    prov = skill_admin_store.get_provenance(name)
    immutable_warning = False
    if prov["source"] == "managed":
        skill_admin_store.mark_drift(name)
        # a heuristic: editing always touches the body; flag if the skill declares
        # any immutable fields so the UI can warn the change will be reverted.
        immutable_warning = skill_admin_store.is_immutable_change(name, {"name", "content"})
    verdict = engine_audit(body.content)
    result = _publish(name, body.content, prov["source"], verdict)
    result["immutable_warning"] = immutable_warning
    result["drift"] = prov["source"] == "managed"
    audit_log.write_audit(user.id, "skill.edit", "skill", name, detail=result)
    return result


# --- global enable / disable + hot reload ------------------------------------


@router.post("/{name}/disable")
def disable_skill(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    skill_admin_store.set_global_enabled(name, False)
    engine_set_global_disabled(name, True)
    audit_log.write_audit(user.id, "skill.disable", "skill", name)
    return {"name": name, "global_enabled": 0}


@router.post("/{name}/enable")
def enable_skill(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    skill_admin_store.set_global_enabled(name, True)
    engine_set_global_disabled(name, False)
    audit_log.write_audit(user.id, "skill.enable", "skill", name)
    return {"name": name, "global_enabled": 1}


@router.post("/reload")
def reload_skills(authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = engine_reload()
    audit_log.write_audit(user.id, "skill.reload", "skill", None, detail=result)
    if not result.get("ok"):
        raise HTTPException(status_code=503, detail=result.get("error", "reload failed"))
    return result


# --- archive (soft delete) + reference protection + restore -------------------


@router.delete("/{name}")
def archive_skill(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    occupants = skill_admin_store.agents_enabling(name)
    if occupants:
        raise HTTPException(
            status_code=409,
            detail={"error": "skill still enabled by agents", "agents": occupants},
        )
    _require_confirm(x_confirm)
    skill_admin_store.set_status(name, "archived")
    audit_log.write_audit(user.id, "skill.archive", "skill", name)
    return {"name": name, "status": "archived"}


@router.post("/{name}/restore")
def restore_skill(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    skill_admin_store.set_status(name, "active")
    audit_log.write_audit(user.id, "skill.restore", "skill", name)
    return {"name": name, "status": "active"}


# --- Skill ↔ Agent binding matrix --------------------------------------------


@router.get("/{name}/agents")
def list_skill_agents(name: str, authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return skill_admin_store.list_agents_for_skill(name)


@router.put("/{name}/agents/{agent_id}")
def set_skill_agent_binding(
    name: str, agent_id: str, body: BindingBody, authorization: str | None = Header(None)
) -> dict[str, Any]:
    user = _require_admin(authorization)
    skill_admin_store.set_binding(agent_id, name, body.enabled, updated_by=user.id)
    action = "skill.agent_enable" if body.enabled else "skill.agent_disable"
    audit_log.write_audit(user.id, action, "skill", name, detail={"agent_id": agent_id})
    return {"name": name, "agent_id": agent_id, "enabled": body.enabled}


# --- security-audit quarantine + force-publish --------------------------------


@router.post("/{name}/force-publish")
def force_publish(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    skill_admin_store.set_forced(name, True)
    skill_admin_store.set_status(name, "active")
    engine_reload()
    audit_log.write_audit(user.id, "skill.force_publish", "skill", name)
    return {"name": name, "status": "active", "forced": 1}


# --- per-skill observation ----------------------------------------------------


@router.get("/{name}/observability")
def skill_observability(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return engine_observability(name)


# --- provenance promote / discard --------------------------------------------


@router.post("/{name}/provenance/promote")
def promote_skill(
    name: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    result = askit_override(name, "promote")
    skill_admin_store.clear_drift(name)
    audit_log.write_audit(user.id, "skill.promote", "skill", name, detail=result)
    return result


@router.post("/{name}/provenance/discard")
def discard_skill(name: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    user = _require_admin(authorization)
    result = askit_override(name, "discard")
    skill_admin_store.clear_drift(name)
    audit_log.write_audit(user.id, "skill.discard", "skill", name, detail=result)
    return result


# --- reflection proposal inbox ------------------------------------------------


@router.get("/proposals")
def list_proposals(authorization: str | None = Header(None)) -> list[dict[str, Any]]:
    _current_user(authorization)
    return reflection_list_proposals()


@router.get("/proposals/{proposal_id}/diff")
def proposal_diff(proposal_id: str, authorization: str | None = Header(None)) -> dict[str, Any]:
    _current_user(authorization)
    return reflection_proposal_diff(proposal_id)


@router.post("/proposals/{proposal_id}/approve")
def approve_proposal(
    proposal_id: str,
    authorization: str | None = Header(None),
    x_confirm: str | None = Header(None),
) -> dict[str, Any]:
    user = _require_admin(authorization)
    _require_confirm(x_confirm)
    reflection_apply_proposal(proposal_id, user.id)
    audit_log.write_audit(user.id, "skill.proposal_approve", "skill_proposal", proposal_id)
    return {"proposal_id": proposal_id, "status": "approved"}


class RejectBody(BaseModel):
    reason: str = "rejected via admin console"


@router.post("/proposals/{proposal_id}/reject")
def reject_proposal(
    proposal_id: str,
    authorization: str | None = Header(None),
    body: RejectBody | None = None,
) -> dict[str, Any]:
    user = _require_admin(authorization)
    reason = body.reason if body else "rejected via admin console"
    reflection_close_proposal(proposal_id, user.id, reason)
    audit_log.write_audit(user.id, "skill.proposal_reject", "skill_proposal", proposal_id)
    return {"proposal_id": proposal_id, "status": "rejected"}
