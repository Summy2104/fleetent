"""Skill registry: scan skills/, match user input, load SKILL.md content."""

import os
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
import yaml

from fleetent.skills import audit as skill_audit

logger = structlog.get_logger(__name__)


# Platform-shipped builtin skills live inside the package so a fresh deployment
# is non-empty. Module-level path constant (injectable via monkeypatch per the
# project's no-global-mutable-state rule). This module lives in skills/, so the
# builtin directory is one level up at src/fleetent/builtin_skills/.
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "builtin_skills"


@dataclass
class SkillEntry:
    """Indexed metadata for a single skill, parsed from SKILL.md frontmatter."""

    description: str
    path: str
    tags: list[str] = field(default_factory=list)
    platforms: list[str] = field(default_factory=list)
    version: str | None = None
    enabled_by_default: bool = True
    # Author-level hard kill from frontmatter `enabled: false`; wins over
    # enabled_by_default (a default-state hint). Excludes the skill from the
    # catalog; load() ignores it (manual access stays open).
    enabled: bool = True
    builtin: bool = False
    # Set when the SKILL.md body or description hits a `severe` injection pattern
    # (skill-injection-audit). The entry stays in `_index` but is excluded from the
    # catalog and refused by read_skill; load() ignores this flag (manual triage).
    audit_blocked: bool = False
    # Author hint: hide from the <available_skills> catalog (the model won't discover
    # it) while keeping read_skill able to load it by name — for internal/composed
    # skills invoked by other skills or hooks. Orthogonal to audit_blocked (a security
    # block that read_skill refuses); this is discovery-only.
    disable_model_invocation: bool = False
    # Tool names this skill depends on. Filtered at catalog RENDER time against the
    # session's available tool set (tool availability varies per session), not at scan.
    requires_tools: list[str] = field(default_factory=list)
    # Env vars needed before the skill can run, each {"name", optional?: bool}. Metadata
    # only — surfaced by skill_readiness(); never blocks the catalog.
    required_env_vars: list[dict[str, Any]] = field(default_factory=list)
    # Standard Agent Skills `compatibility` field (free-text environment requirement).
    # Recognized and carried so it is a known field rather than ignored; this change
    # only identifies + carries it (no runtime matching semantics here).
    compatibility: str | None = None


_index: dict[str, SkillEntry] = {}
_last_skills_dir: str | None = None

# Skills skipped during the last scan() because their SKILL.md could not be parsed.
# A malformed skill is isolated (skipped, never crashes the scan) but recorded here
# and summarized so operators can answer "why didn't this skill load?" — surface via
# load_errors() from an admin command or health check.
_load_errors: list[dict[str, str]] = []

_STOP_WORDS = {"the", "a", "an", "when", "use", "for", "to", "and", "or", "is", "are", "want"}


@dataclass(frozen=True)
class SkillWriteProvenance:
    """Audit metadata injected into a reflected skill bundle."""

    source: str
    proposal_id: str
    applied_at: str


def _resolve_skills_dir(skills_dir: str | None) -> str:
    """Return the user skills directory, falling back to env then ``<home>/skills``."""
    if skills_dir is None:
        from fleetent import paths

        return os.environ.get("FLEETENT_SKILLS_DIR") or str(paths.base_dir() / "skills")
    return skills_dir


def effective_skill_root(skills_dir: str | None = None) -> str:
    """Return the single effective skills root mounted at /workspace/skills (D3).

    `/workspace/skills` can bind only one host dir, while the index draws from two
    physical roots (package `BUILTIN_SKILLS_DIR` + the user root). The effective root
    is the USER root (operator-writable, customizable, where `write_skill` lands), so
    builtin skills are materialized into it (`materialize_builtin_skills`) rather than
    the package dir being mounted. Idempotent: creates the root if missing.
    """
    resolved = _resolve_skills_dir(skills_dir)
    Path(resolved).mkdir(parents=True, exist_ok=True)
    return resolved


def materialize_builtin_skills(skills_dir: str | None = None) -> None:
    """Copy package builtin skills into the effective (user) root, idempotently (D3).

    So a builtin skill's same-directory resources are reachable under
    `$SKILLS_DIR/<name>/` once the user root is mounted at /workspace/skills. A user
    skill of the same name is never overwritten (sustains the user-overrides-builtin
    semantics): a destination dir that already exists is left untouched. A copy
    failure is logged (never silently swallowed) and skipped so one bad builtin
    cannot abort the rest or block the mount.
    """
    root = Path(effective_skill_root(skills_dir))
    if not BUILTIN_SKILLS_DIR.is_dir():
        return
    for src in BUILTIN_SKILLS_DIR.iterdir():
        if not src.is_dir() or not (src / "SKILL.md").is_file():
            continue
        dest = root / src.name
        if dest.exists():
            # User-authored (or already-materialized) skill of this name wins; do not
            # clobber operator customization with the package copy.
            continue
        try:
            shutil.copytree(src, dest)
        except OSError as exc:
            logger.warning("skill_materialize_failed", name=src.name, error=str(exc))


def _build_index(
    skills_dir: str | None = None,
    errors: list[dict[str, str]] | None = None,
) -> dict[str, SkillEntry]:
    """Build a fresh skill index from builtin + user directories without touching globals.

    Traverses both the package builtin directory (`BUILTIN_SKILLS_DIR`) and the
    user `skills/` directory with the same frontmatter parsing, merging both
    sources into one new dict. Source is recorded on each entry via `builtin`;
    same-name conflicts (within or across sources) are resolved by
    `skill-name-conflict-warning` (SK8) path-sort, never by source priority.

    Returns the new index. The module-level `_index` is never mutated —
    decoupling construction from publication is what lets `reload()` build
    safely and only then swap atomically (or, on failure, keep the old index).
    When `errors` is provided, skipped (unparseable) skills are appended to it
    so `scan()` can keep populating `load_errors()`.
    """
    resolved = _resolve_skills_dir(skills_dir)
    index: dict[str, SkillEntry] = {}
    sink: list[dict[str, str]] = errors if errors is not None else []
    _scan_dir(BUILTIN_SKILLS_DIR, index, sink, builtin=True)
    _scan_dir(Path(resolved), index, sink, builtin=False)
    return index


def scan(skills_dir: str | None = None) -> None:
    """Scan platform builtin and user skills directories, building name → SkillEntry.

    Both the package builtin directory and the user `skills/` directory are
    traversed with the same frontmatter parsing. Source is recorded on each
    entry via `builtin`; same-name conflicts (within or across sources) are
    resolved by `skill-name-conflict-warning` (SK8) path-sort, never by source
    priority — this change introduces no override rule of its own.
    """
    new_errors: list[dict[str, str]] = []
    new_index = _build_index(skills_dir, new_errors)
    global _last_skills_dir
    _last_skills_dir = _resolve_skills_dir(skills_dir)
    _index.clear()
    _index.update(new_index)
    _load_errors.clear()
    _load_errors.extend(new_errors)
    # Emit the summary only when something failed: a clean scan stays silent (the
    # common startup path), and the actionable "N skills failed to load" line is the
    # only one logged. Counts also available structured via load_errors().
    if _load_errors:
        logger.warning("skill_scan_complete", loaded=len(_index), failed=len(_load_errors))


def reload(skills_dir: str | None = None) -> dict[str, Any]:
    """Rescan skills at runtime and atomically swap in the new index.

    Builds a brand-new index via `_build_index` and, only on success, rebinds
    the module-level `_index` to it in a single assignment (D2). Because the
    rebind is atomic, any concurrent read sees either the complete old index or
    the complete new one — never a half-filled intermediate. On any error
    (missing directory, parse-time crash) the old index is left untouched and a
    structured warning is logged (D3); the service keeps serving the old skills
    rather than degrading to empty.

    Returns a summary: ``{"status": "ok", "loaded": N, "failed": M}`` on success,
    or ``{"status": "failed", "skills_dir": ..., "reason": ...}`` on failure.
    """
    global _index, _load_errors, _last_skills_dir
    resolved = _resolve_skills_dir(skills_dir)
    new_errors: list[dict[str, str]] = []
    try:
        new_index = _build_index(resolved, new_errors)
    except Exception as exc:
        logger.warning("skill_reload_failed", skills_dir=resolved, reason=str(exc))
        return {"status": "failed", "skills_dir": resolved, "reason": str(exc)}
    # Atomic publication: a single name rebind, visible at once to every reader
    # (all access `_index` through the module, none capture it at def time).
    _index = new_index
    _load_errors = new_errors
    _last_skills_dir = resolved
    if new_errors:
        logger.warning("skill_reload_complete", loaded=len(new_index), failed=len(new_errors))
    return {"status": "ok", "loaded": len(new_index), "failed": len(new_errors)}


def write_skill(
    name: str,
    files: dict[str, str],
    provenance: SkillWriteProvenance,
    *,
    skills_dir: str | None = None,
) -> Path:
    """Atomically write one full skill bundle and hot-reload the registry."""
    resolved_root = Path(skills_dir or _last_skills_dir or _resolve_skills_dir(None))
    if "SKILL.md" not in files:
        raise ValueError("skill bundle must include SKILL.md")

    skill_root = resolved_root / name
    tmp_parent = resolved_root / ".tmp"
    tmp_parent.mkdir(parents=True, exist_ok=True)
    resolved_root.mkdir(parents=True, exist_ok=True)

    tmp_dir = Path(tempfile.mkdtemp(prefix=f"{name}-", dir=tmp_parent))
    try:
        for relpath, content in files.items():
            dest = tmp_dir / relpath
            dest.parent.mkdir(parents=True, exist_ok=True)
            if relpath == "SKILL.md":
                content = _inject_skill_provenance(content, provenance)
                _validate_skill_bundle(content, str(dest))
            dest.write_text(content, encoding="utf-8")

        backup_dir = skill_root.with_name(f"{skill_root.name}.bak")
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        if skill_root.exists():
            skill_root.rename(backup_dir)
        tmp_dir.rename(skill_root)
        if backup_dir.exists():
            shutil.rmtree(backup_dir)
        reload(str(resolved_root))
        return skill_root
    except Exception:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def load_errors() -> list[dict[str, str]]:
    """Return the skills skipped during the last scan() as {path, reason, source}.

    Empty when every SKILL.md parsed cleanly. Lets an admin command or health check
    surface load failures beyond the per-skill warning logs.
    """
    return list(_load_errors)


def _scan_dir(
    base: Path,
    index: dict[str, SkillEntry],
    errors: list[dict[str, str]],
    *,
    builtin: bool,
) -> None:
    """Index every SKILL.md under base into `index`, tagging entries with their source.

    Operates on the passed-in `index`/`errors` so the same traversal serves both
    the in-place `scan()` path and the build-then-swap `_build_index()` path.
    """
    if not base.is_dir():
        return
    # followlinks=True ensures symlinked skill directories are traversed (Python
    # Path.rglob does not follow symlinks by default until 3.13).
    for root, _dirs, files in os.walk(base, followlinks=True):
        if "SKILL.md" not in files:
            continue
        skill_md = Path(root) / "SKILL.md"
        raw = skill_md.read_text(encoding="utf-8")
        frontmatter = _parse_frontmatter(raw)
        if frontmatter is None:
            reason = "missing --- boundary, invalid YAML, or non-mapping top level"
            source = "builtin" if builtin else "user"
            logger.warning(
                "skill_frontmatter_parse_failed",
                path=str(skill_md),
                reason=reason,
                source=source,
            )
            errors.append({"path": str(skill_md), "reason": reason, "source": source})
            continue
        name = frontmatter.get("name") or skill_md.parent.name
        path = str(skill_md)
        existing = index.get(name)
        if existing is not None:
            # Deterministic selection independent of traversal order. Tier precedence
            # first: a user skill (builtin=False) overrides a same-name builtin one so
            # operators can predictably customize a builtin — regardless of path sort.
            # Within the same tier, fall back to SK8 path-string sort (smaller wins).
            tier_override = existing.builtin != builtin
            # When tiers differ the user one wins. `builtin` is the NEW entry's tier:
            # new is builtin (True) -> keep existing(user); new is user (False) ->
            # overwrite existing(builtin). Both cases reduce to keep_existing = builtin.
            # Same tier: SK8 path-string sort (smaller path wins).
            keep_existing = builtin if tier_override else existing.path <= path
            kept_path = existing.path if keep_existing else path
            dropped_path = path if keep_existing else existing.path
            logger.warning(
                "skill_name_conflict",
                name=name,
                kept_path=kept_path,
                dropped_path=dropped_path,
                tier_override=tier_override,
            )
            if keep_existing:
                continue
        description = str(frontmatter.get("description", ""))
        blocked = _audit_skill(path, _body_after_frontmatter(raw), description)
        index[name] = _build_entry(frontmatter, description, path, builtin, blocked)


def _build_entry(
    frontmatter: dict[str, Any],
    description: str,
    path: str,
    builtin: bool,
    blocked: bool,
) -> SkillEntry:
    """Construct a SkillEntry, resolving each extension field per the standard protocol.

    For every fleetent extension the resolution order is fixed (D1):
    `metadata.fleetent-<key>` (standard, authoritative) → legacy top-level `<key>`
    (backward-compatible fallback) → default. `metadata` values are strings (D2):
    bools as `"true"`/`"false"`, lists as space-separated, env optional via `name?`.
    A non-`fleetent-` `metadata` key or an unrecognized `fleetent-*` key is ignored
    (D4: graceful degradation). The standard `compatibility` field is carried (D3).
    """
    meta = frontmatter.get("metadata")
    if not isinstance(meta, dict):
        meta = {}

    def _list_field(meta_key: str, legacy_key: str) -> list[str]:
        if meta_key in meta:
            return _split_ws(meta[meta_key])
        return _as_str_list(frontmatter.get(legacy_key))

    def _bool_field(meta_key: str, legacy_key: str, default: bool) -> bool:
        decoded = _as_bool_meta(meta.get(meta_key))
        if decoded is not None:
            return decoded
        return bool(frontmatter.get(legacy_key, default))

    if "fleetent-required-env" in meta:
        required_env_vars = _as_env_var_list_from_meta(meta["fleetent-required-env"])
    else:
        required_env_vars = _as_env_var_list(frontmatter.get("required_env_vars"))

    if "fleetent-version" in meta:
        version = _as_opt_str(meta["fleetent-version"])
    else:
        version = _as_opt_str(frontmatter.get("version"))

    return SkillEntry(
        description=description,
        path=path,
        tags=_list_field("fleetent-tags", "tags"),
        platforms=_list_field("fleetent-platforms", "platforms"),
        version=version,
        enabled_by_default=_bool_field("fleetent-enabled-by-default", "enabled_by_default", True),
        enabled=_bool_field("fleetent-enabled", "enabled", True),
        builtin=builtin,
        audit_blocked=blocked,
        disable_model_invocation=_bool_field(
            "fleetent-disable-model-invocation", "disable_model_invocation", False
        ),
        requires_tools=_list_field("fleetent-requires-tools", "requires_tools"),
        required_env_vars=required_env_vars,
        compatibility=_as_opt_str(frontmatter.get("compatibility")),
    )


def _validate_skill_bundle(content: str, path: str) -> None:
    frontmatter = _parse_frontmatter(content)
    if frontmatter is None:
        raise ValueError("SKILL.md must contain valid frontmatter")
    description = str(frontmatter.get("description", ""))
    if _audit_skill(path, _body_after_frontmatter(content), description):
        raise ValueError("SKILL.md failed severe injection audit")


def _inject_skill_provenance(content: str, provenance: SkillWriteProvenance) -> str:
    frontmatter = _parse_frontmatter(content)
    if frontmatter is None:
        raise ValueError("SKILL.md must contain valid frontmatter")
    frontmatter["source"] = provenance.source
    frontmatter["proposal_id"] = provenance.proposal_id
    frontmatter["applied_at"] = provenance.applied_at
    body = _body_after_frontmatter(content).lstrip("\n")
    return f"---\n{yaml.safe_dump(frontmatter, sort_keys=False).strip()}\n---\n{body}"


def _body_after_frontmatter(raw: str) -> str:
    """Return the SKILL.md content following the closing frontmatter delimiter.

    Falls back to the whole text when no `---`-delimited frontmatter is present,
    so the audit never silently skips content it should scan.
    """
    if not raw.startswith("---"):
        return raw
    parts = raw.split("---", 2)
    return parts[2] if len(parts) >= 3 else raw


def _audit_skill(path: str, body: str, description: str) -> bool:
    """Run the static injection audit and record one structured log per hit.

    Returns True when any `severe` pattern hit (the caller sets `audit_blocked`).
    `severe` hits log at warning with disposition "blocked"; `suspicious` hits log
    at warning with disposition "allowed" so a startup scan surfaces both on the
    console while the skill stays usable.
    """
    hits = skill_audit.audit(body, description)
    if not hits:
        return False
    blocked = skill_audit.has_severe(hits)
    for hit in hits:
        disposition = "blocked" if hit.severity == skill_audit.SEVERE else "allowed"
        logger.warning(
            "skill_audit_hit",
            path=path,
            rule_id=hit.rule_id,
            severity=hit.severity,
            field=hit.field,
            disposition=disposition,
        )
    return blocked


def match(user_input: str, disabled_skills: list[str] | None = None) -> str | None:
    """Return the first enabled skill whose description keywords appear in user_input.

    A skill is excluded from matching (and not auto-injected) when it is
    disabled — either `enabled_by_default` is false, or its name is in
    `disabled_skills`. The exclusion reason is logged so operators can answer
    "why didn't this skill fire?". `disabled_skills` defaults to the active agent's
    `disabled_skills` (param > config); `load()` is unaffected.
    """
    disabled = _resolve_disabled_skills(disabled_skills)
    lowered = user_input.lower()
    for name, entry in _index.items():
        keywords = {
            w.strip(".,!?").lower()
            for w in entry.description.split()
            if len(w) > 4 and w.lower() not in _STOP_WORDS
        }
        if not any(kw in lowered for kw in keywords):
            continue
        reason = _disabled_reason(name, entry, disabled)
        if reason is not None:
            logger.info("skill_disabled_skipped", name=name, reason=reason, builtin=entry.builtin)
            continue
        return name
    return None


def _resolve_disabled_skills(disabled_skills: list[str] | None) -> set[str]:
    """Resolve the force-disable name set: explicit param > active agent config."""
    if disabled_skills is not None:
        return set(disabled_skills)
    from fleetent import agent_config

    return set(agent_config.active_agent_or_default().disabled_skills)


def _disabled_reason(name: str, entry: SkillEntry, disabled: set[str]) -> str | None:
    """Return the first matching disable source identifier, or None when eligible.

    This is the single eligibility predicate that decides whether a skill enters
    the `available_skills_prompt` catalog; every catalog/match filter routes
    through it so the disable sources are judged in exactly one place.
    Sources are checked in priority order — security first, author intent next,
    operator config, then the author's default-state hint:
    `audit_blocked` > `model_invocation_disabled` (`disable_model_invocation: true`) >
    `frontmatter_disabled` (`enabled: false`) > `config_disabled` (`disabled_skills`) >
    `default_disabled` (`enabled_by_default: false`). The returned identifier is the
    highest-priority
    match and is the value recorded in the run trace.
    """
    if entry.audit_blocked:
        return "audit_blocked"
    if entry.disable_model_invocation:
        # Author hid it from model discovery; read_skill (which ignores this predicate)
        # can still load it by name for internal/composed use.
        return "model_invocation_disabled"
    if not entry.enabled:
        return "frontmatter_disabled"
    if name in disabled:
        return "config_disabled"
    if not entry.enabled_by_default:
        return "default_disabled"
    return None


def _tools_available(entry: SkillEntry, available_tools: set[str] | None) -> bool:
    """Whether the skill's `requires_tools` are all in the session's available set.

    Render-time gate (tool availability varies per session), orthogonal to the
    scan-time `_disabled_reason`. `available_tools is None` means "don't filter"
    (backward compatible) so callers that can't compute the set keep prior behavior.
    """
    if available_tools is None or not entry.requires_tools:
        return True
    return all(tool in available_tools for tool in entry.requires_tools)


def skill_readiness(name: str) -> dict[str, list[str]]:
    """Report a skill's missing required env vars (skill-frontmatter-extensions).

    Returns ``{"missing": [names]}`` for each non-optional `required_env_vars` entry
    not present in the process environment. Metadata only — never affects the catalog
    or read_skill; powers an admin-console readiness view. Unknown skill → empty.
    """
    entry = _index.get(name)
    if entry is None:
        return {"missing": []}
    missing = [
        var["name"]
        for var in entry.required_env_vars
        if not var.get("optional", False) and var["name"] not in os.environ
    ]
    return {"missing": missing}


# Mandatory scan instruction that precedes the <available_skills> catalog. Skills
# are surfaced as a discoverable list (name/description/location); the model loads
# the full SKILL.md on demand via read_skill rather than the platform auto-injecting
# content. Stable across requests, so it sits in the cacheable system prefix.
_SKILLS_INSTRUCTION = (
    "## Skills\n"
    "The following skills provide specialized instructions for specific tasks. "
    "When exactly one skill's description clearly matches the task, call the "
    "`read_skill` tool with its <name> to load the full SKILL.md, then follow it. "
    "If several could apply, pick the most specific one. If none clearly apply, "
    "do not read any. "
    "Run any skill script via the container execution tool (`run_code`); inside it, "
    "resolve skill paths under `$SKILLS_DIR` (= /workspace/skills), e.g. run_code calling "
    "subprocess on `$SKILLS_DIR/<name>/script.py`."
)

# Fixed guidance appended to a successful read_skill load (skill-read-on-demand): run
# the skill's scripts via run_code and resolve paths under $SKILLS_DIR. Constant text so
# the addition does not vary per skill.
_READ_SKILL_GUIDANCE = (
    "\n\n---\n"
    "[执行提示] 该 Skill 的脚本须经容器内执行面 `run_code` 运行；脚本内路径以 "
    "`$SKILLS_DIR`（= /workspace/skills）为根，例如 `$SKILLS_DIR/<name>/script.py`。"
)

# Container-side skills root the catalog renders locations against (sandbox-skill-mount):
# the model sees a single /workspace world, so a skill's location is shown as
# `$SKILLS_DIR/<rel>` rather than a host-absolute path it cannot reach.
_SKILLS_DIR_PLACEHOLDER = "$SKILLS_DIR"


def _location_under_skills_dir(entry_path: str) -> str:
    """Render a skill's SKILL.md location as a `$SKILLS_DIR`-rooted path (D3/D7).

    Computes the path relative to the effective skills root when the SKILL.md lives
    under it; otherwise falls back to `<dir-name>/SKILL.md` (a builtin materialized
    into the root keeps the same basename). Never emits a host-absolute path.
    """
    p = Path(entry_path)
    root = Path(_last_skills_dir) if _last_skills_dir else None
    rel: str | None = None
    if root is not None:
        try:
            rel = str(p.relative_to(root))
        except ValueError:
            rel = None
    if rel is None:
        rel = f"{p.parent.name}/{p.name}"
    return f"{_SKILLS_DIR_PLACEHOLDER}/{rel}"


def available_skills_prompt(
    disabled_skills: list[str] | None = None,
    allowed_skills: list[str] | None = None,
    max_skills: int = 150,
    max_chars: int = 18000,
    available_tools: set[str] | None = None,
) -> str:
    """Render the enabled skills as an openclaw-style skills section for the prompt.

    Returns the mandatory scan instruction followed by an <available_skills>
    catalog listing each enabled skill's name, description, and SKILL.md location,
    so the model can discover what exists and load the full file on demand via the
    read_skill tool — instead of the platform auto-injecting full content. A skill
    is omitted when the single eligibility predicate (`_disabled_reason`) reports
    any disable source — `audit_blocked`, `enabled: false`, config force-disable,
    or `enabled_by_default: false` — so its name/description never reach the prompt.
    Returns "" when nothing is enabled, so the caller can drop the section entirely
    (keeping the cache prefix maximal).

    `allowed_skills` is a per-agent catalog-visibility narrowing (agent-skill-scoping):
    empty / None means no narrowing (every enabled skill stays visible, preserving the
    pre-change default where skills are visible to all agents — the OPPOSITE default
    from `plugins`). A non-empty list keeps only skills whose name is listed, AND-ed
    with the disable predicate so a disabled skill never appears even when listed
    (disable wins). This narrows catalog visibility only; it is NOT an authorization
    boundary — `read_skill`'s by-name `load` and tool access control are unaffected.

    `max_skills` / `max_chars` bound the catalog so a growing skill library cannot
    silently bloat the cached system-prefix (skill-catalog-budget). When the eligible
    count exceeds `max_skills` the catalog is truncated to the first N and a warning
    line (naming shown vs total) precedes the instruction. When the full-format render
    exceeds `max_chars` it falls back to a compact format (name + location, no
    description); a still-oversized compact render is further truncated by count.
    Truncated skills remain loadable by name via read_skill — the catalog is a
    discovery surface, not an authorization boundary. Defaults are large enough that
    typical deployments render byte-identically to the pre-budget behavior.
    """
    disabled = _resolve_disabled_skills(disabled_skills)
    allowed = set(allowed_skills) if allowed_skills else None
    entries = [
        (name, entry)
        for name, entry in _index.items()
        if _disabled_reason(name, entry, disabled) is None
        and (allowed is None or name in allowed)
        and _tools_available(entry, available_tools)
    ]
    if not entries:
        return ""

    total = len(entries)
    shown = entries[:max_skills] if total > max_skills else entries

    rendered = _render_catalog(shown, total, compact=False)
    if len(rendered) <= max_chars:
        return rendered
    # Full format blew the char budget: drop descriptions (compact) to keep
    # discoverability cheap. If compact still overruns, trim by count until it fits
    # (always keeping at least one entry so the section stays meaningful).
    while shown:
        compact = _render_catalog(shown, total, compact=True)
        if len(compact) <= max_chars or len(shown) == 1:
            return compact
        shown = shown[: len(shown) - 1]
    return rendered  # unreachable (entries non-empty), keeps type checker happy


def _render_catalog(shown: list[tuple[str, "SkillEntry"]], total: int, *, compact: bool) -> str:
    """Render the <available_skills> section, optionally compact and/or truncated.

    A leading warning line is emitted when fewer than `total` skills are shown or when
    the compact format is used, so the model knows the catalog is reduced.
    """
    lines: list[str] = []
    reduced = len(shown) < total
    if reduced or compact:
        note = f"⚠ Skills: showing {len(shown)} of {total}"
        if reduced:
            note += " (truncated)"
        if compact:
            note += " (compact: names only — read_skill for details)"
        lines.append(note)
        lines.append("")
    lines.extend([_SKILLS_INSTRUCTION, "", "<available_skills>"])
    for name, entry in shown:
        lines.append("  <skill>")
        lines.append(f"    <name>{name}</name>")
        if not compact:
            lines.append(f"    <description>{entry.description}</description>")
        lines.append(f"    <location>{_location_under_skills_dir(entry.path)}</location>")
        lines.append("  </skill>")
    lines.append("</available_skills>")
    return "\n".join(lines)


def collect_disabled_trace(disabled_skills: list[str] | None = None) -> list[dict[str, str]]:
    """Return skills excluded from the catalog as ``[{"name", "reason"}]``.

    Reuses the single eligibility predicate (`_disabled_reason`) over the same
    index `available_skills_prompt` renders, so the trace records exactly the
    skills the model could not see and why (highest-priority source). Returns an
    empty list when every skill is eligible, letting the injection chain omit the
    trace field entirely for the common no-disable run.
    """
    disabled = _resolve_disabled_skills(disabled_skills)
    trace: list[dict[str, str]] = []
    for name, entry in _index.items():
        reason = _disabled_reason(name, entry, disabled)
        if reason is not None:
            trace.append({"name": name, "reason": reason})
    return trace


def load(name: str) -> str:
    """Return full SKILL.md content for the named skill."""
    return Path(_index[name].path).read_text(encoding="utf-8")


def list_skills() -> list[dict[str, str]]:
    """Return all skills as [{"name": ..., "description": ...}]."""
    return [{"name": name, "description": entry.description} for name, entry in _index.items()]


class SkillIndex:
    """An isolated skill index rooted at a single skills directory (per-agent).

    next<-main integration: main's agent runtime builds a SkillIndex from an agent
    version's own ``skills_dir`` so each agent gets an independent catalog without
    touching the module-level ``_index``. Wraps zhangyang's ``_build_index`` so the
    same frontmatter parsing / audit / conflict rules apply; match/load mirror the
    module-level behaviour over this instance's own entries.
    """

    def __init__(
        self,
        skills_dir: str | None = None,
        *,
        scan: bool = True,
        allowed: set[str] | None = None,
    ) -> None:
        self._entries: dict[str, SkillEntry] = {}
        # When set, only these skill names survive scanning (per-agent allowlist).
        self._allowed = allowed
        if scan:
            self.scan(skills_dir)

    def scan(self, skills_dir: str | None = None) -> None:
        entries = _build_index(skills_dir)
        # Apply allowed filtering if set
        if self._allowed is not None:
            self._entries = {k: v for k, v in entries.items() if k in self._allowed}
        else:
            self._entries = entries

    def match(self, user_input: str) -> str | None:
        lowered = user_input.lower()
        for name, entry in self._entries.items():
            # Skip author-disabled / audit-blocked skills (they are not auto-injected).
            if not entry.enabled or not entry.enabled_by_default or entry.audit_blocked:
                continue
            keywords = {
                w.strip(".,!?").lower()
                for w in entry.description.split()
                if len(w) > 4 and w.lower() not in _STOP_WORDS
            }
            if any(kw in lowered for kw in keywords):
                return name
        return None

    def load(self, name: str) -> str:
        return Path(self._entries[name].path).read_text(encoding="utf-8")

    def list_skills(self) -> list[dict[str, str]]:
        return [{"name": n, "description": e.description} for n, e in self._entries.items()]


def _parse_frontmatter(content: str) -> dict[str, Any] | None:
    """Parse YAML frontmatter between leading/trailing --- delimiters.

    Returns the parsed mapping, or None when frontmatter is absent
    (no leading/closing ---), malformed YAML, or not a top-level mapping.
    """
    if not content.startswith("---"):
        return None
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        parsed = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    if not isinstance(parsed, dict):
        return None
    return parsed


def _as_str_list(value: Any) -> list[str]:
    """Normalize a scalar/list/missing value into a list of strings."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    return [str(value)]


def _as_opt_str(value: Any) -> str | None:
    """Normalize a scalar/missing value into an optional string."""
    if value is None:
        return None
    return str(value)


def _as_env_var_list(value: Any) -> list[dict[str, Any]]:
    """Normalize `required_env_vars` into a list of {"name", optional} dicts.

    Each item must be a mapping with a `name`; non-mapping or name-less items are
    skipped. `optional` defaults to False. Missing/non-list input yields [].
    """
    if not isinstance(value, list):
        return []
    out: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not name:
            continue
        out.append({"name": str(name), "optional": bool(item.get("optional", False))})
    return out


def _as_bool_meta(value: Any) -> bool | None:
    """Decode a `metadata` string into a bool, or None when unrecognized.

    `metadata` is string→string per the Agent Skills protocol, so booleans are
    encoded as `"true"`/`"false"` (case-insensitive). Any other value (including
    None or non-str) returns None so the caller falls back to the legacy field or
    the default rather than silently flipping semantics.
    """
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _split_ws(value: Any) -> list[str]:
    """Split a whitespace-delimited `metadata` string into a list of tokens.

    Empty / whitespace-only / non-str input yields []. This is the string-value
    encoding for list extensions (e.g. `fleetent-tags: "intro onboarding help"`).
    """
    if not isinstance(value, str):
        return []
    return value.split()


def _as_env_var_list_from_meta(value: Any) -> list[dict[str, Any]]:
    """Decode `fleetent-required-env` (space-separated names) into env-var dicts.

    Each token is a variable name; a trailing `?` marks it optional (POSIX env
    names never contain `?`, so the marker is unambiguous). Produces the same
    shape as `_as_env_var_list` so downstream `skill_readiness` is unchanged.
    """
    out: list[dict[str, Any]] = []
    for token in _split_ws(value):
        if token.endswith("?"):
            out.append({"name": token[:-1], "optional": True})
        else:
            out.append({"name": token, "optional": False})
    return out
