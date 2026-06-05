from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import yaml

from fleetent import paths
from fleetent.config import MCP_SERVERS_YAML_PATH, SETTINGS_YAML_PATH, Settings

if TYPE_CHECKING:
    from fleetent.agent_config import AgentFile

ValidationProfile = Literal["dev", "pilot", "production"]
ValidationStatus = Literal["pass", "warning", "skipped", "error"]

_SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{10,}|xox[baprs]-[A-Za-z0-9-]{10,}|"
    r"bearer\s+[A-Za-z0-9._-]{10,}|[A-Za-z0-9_-]{24,})",
    re.IGNORECASE,
)
_PLACEHOLDER_RE = re.compile(
    r"(example|placeholder|changeme|replace-me|<.*>|\\$\\{|env:|file://)", re.IGNORECASE
)


@dataclass(frozen=True)
class ValidationItem:
    key: str
    status: ValidationStatus
    reason: str

    def to_json(self) -> dict[str, str]:
        return asdict(self)


@dataclass(frozen=True)
class ValidationReport:
    profile: ValidationProfile
    items: list[ValidationItem]

    @property
    def summary(self) -> dict[str, int]:
        return {
            "error": sum(item.status == "error" for item in self.items),
            "pass": sum(item.status == "pass" for item in self.items),
            "skipped": sum(item.status == "skipped" for item in self.items),
            "warning": sum(item.status == "warning" for item in self.items),
        }

    @property
    def final_status(self) -> Literal["pass", "warning", "error"]:
        if self.summary["error"]:
            return "error"
        if self.summary["warning"]:
            return "warning"
        return "pass"

    def to_dict(self) -> dict[str, object]:
        return {
            "final_status": self.final_status,
            "items": [item.to_json() for item in sorted(self.items, key=lambda item: item.key)],
            "profile": self.profile,
            "summary": self.summary,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)


def validate_config(
    *,
    profile: ValidationProfile,
    settings: Settings | None = None,
    agent: AgentFile | None = None,
    data_dir: Path | None = None,
    config_dir: Path | None = None,
    secrets_dir: Path | None = None,
    config_paths: list[Path] | None = None,
    scan_resolved_agent: bool = False,
) -> ValidationReport:
    """Validate local runtime prerequisites without creating production data.

    Platform prerequisites (DB reachability, directories) come from the slim
    ``Settings``; agent-runtime dependencies (intelligence backends, connector refs)
    and the resolved-config secret scan come from the per-agent ``agent.yaml``."""
    resolved = settings or Settings()
    if agent is None:
        from fleetent import agent_config

        agent = agent_config.active_agent_or_default()
    items: list[ValidationItem] = []
    items.extend(_runtime_items(resolved, data_dir, config_dir, secrets_dir))
    items.extend(_profile_items(profile, agent))
    items.extend(_config_secret_scan_items(config_paths))
    if scan_resolved_agent:
        items.extend(_secret_scan_items(agent))
    return ValidationReport(profile=profile, items=items)


def render_text(report: ValidationReport) -> str:
    lines = [
        f"profile={report.profile}",
        f"final_status={report.final_status}",
        "summary=" + " ".join(f"{key}={value}" for key, value in sorted(report.summary.items())),
    ]
    for item in sorted(report.items, key=lambda value: value.key):
        lines.append(f"{item.status:<7} {item.key} {item.reason}")
    return "\n".join(lines)


def _runtime_items(
    settings: Settings,
    data_dir: Path | None,
    config_dir: Path | None,
    secrets_dir: Path | None,
) -> list[ValidationItem]:
    items = [ValidationItem("database.url", "pass", _database_reason(settings.database_url))]
    for key, path in {
        "paths.data_dir": data_dir or paths.data_dir(),
        "paths.config_dir": config_dir or paths.config_dir(),
        "paths.secrets_dir": secrets_dir or Path("secrets"),
    }.items():
        if path.exists():
            status: ValidationStatus = "pass" if path.is_dir() else "error"
            reason = "directory exists" if path.is_dir() else "path is not a directory"
        else:
            status = "warning"
            reason = "directory is missing"
        items.append(ValidationItem(key, status, reason))
    return items


def _profile_items(profile: ValidationProfile, agent: AgentFile) -> list[ValidationItem]:
    items: list[ValidationItem] = []
    items.append(
        _dependency_item(profile, "embedding.backend", agent.embedding.backend, "deterministic")
    )
    items.append(_dependency_item(profile, "rerank.backend", agent.rerank.backend, "disabled"))
    if agent.knowledge_base.google_drive.connectors or agent.knowledge_base.confluence.connectors:
        items.append(
            ValidationItem("connectors.credential_ref", "pass", "connector refs configured")
        )
    elif profile == "production":
        items.append(
            ValidationItem(
                "connectors.credential_ref", "error", "production requires connector refs"
            )
        )
    elif profile == "pilot":
        items.append(
            ValidationItem(
                "connectors.credential_ref",
                "skipped",
                "optional real smoke credential refs are absent",
            )
        )
    else:
        items.append(ValidationItem("connectors.credential_ref", "warning", "no connector refs"))
    return items


def _dependency_item(
    profile: ValidationProfile,
    key: str,
    value: str,
    local_default: str,
) -> ValidationItem:
    if value != local_default and value:
        return ValidationItem(key, "pass", f"{value} configured")
    if profile == "production":
        return ValidationItem(key, "error", f"production requires non-{local_default} backend")
    if profile == "pilot":
        return ValidationItem(key, "skipped", f"optional real smoke uses {local_default} backend")
    return ValidationItem(key, "warning", f"dev profile uses {local_default} backend")


def _secret_scan_items(agent: AgentFile) -> list[ValidationItem]:
    payload = agent.model_dump(mode="json")
    items: list[ValidationItem] = []
    for key, value in _flatten(payload):
        if isinstance(value, str) and _looks_inline_secret(value):
            items.append(ValidationItem(f"agent.{key}", "error", "inline secret-like value"))
    return items


def _default_scan_paths() -> list[Path]:
    """Config files scanned for inline secrets by default: platform settings, the MCP
    server file, and every discoverable per-agent ``agent.yaml`` (single- + multi-agent)."""
    from fleetent import agent_config

    scan = [SETTINGS_YAML_PATH, MCP_SERVERS_YAML_PATH, paths.agent_file()]
    root = agent_config._resolve_agents_dir(None)
    if root.is_dir():
        scan.extend(
            agent_dir / agent_config.AGENT_FILE_NAME
            for agent_dir in sorted(root.iterdir())
            if (agent_dir / agent_config.AGENT_FILE_NAME).is_file()
        )
    return scan


def _config_secret_scan_items(config_paths: list[Path] | None) -> list[ValidationItem]:
    scan_paths = config_paths if config_paths is not None else _default_scan_paths()
    items: list[ValidationItem] = []
    for path in scan_paths:
        if not path.exists():
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        for key, value in _flatten(raw):
            if isinstance(value, str) and _looks_inline_secret(value):
                items.append(
                    ValidationItem(
                        f"config.{path}.{key}",
                        "error",
                        "inline secret-like value",
                    )
                )
    return items


def _flatten(value: object, prefix: str = "") -> list[tuple[str, object]]:
    if isinstance(value, dict):
        items: list[tuple[str, object]] = []
        for key, child in value.items():
            next_prefix = f"{prefix}.{key}" if prefix else str(key)
            items.extend(_flatten(child, next_prefix))
        return items
    if isinstance(value, list):
        return [
            item
            for index, child in enumerate(value)
            for item in _flatten(child, f"{prefix}.{index}")
        ]
    return [(prefix, value)]


def _looks_inline_secret(value: str) -> bool:
    if not value or _PLACEHOLDER_RE.search(value):
        return False
    return bool(_SECRET_RE.search(value))


def _database_reason(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        return "sqlite database URL configured"
    return "database URL configured"
