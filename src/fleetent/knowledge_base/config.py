from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from fleetent import paths
from fleetent.secret_scan import flatten, looks_inline_secret

SourceType = Literal["google_drive", "confluence"]
_SECRET_KEY_PARTS = ("token", "secret", "password", "api_key", "credential")


class KnowledgeIndexingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = 1000
    chunk_overlap: int = 200
    parser_profile: str = "default"
    vector_store: str = "default"


class KnowledgeSyncConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schedule: str = ""
    mode: str = "manual"


class KnowledgeSourceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: SourceType
    enabled: bool = True
    tenant_id: str = ""
    kb_id: str = ""
    folder_id: str = ""
    recursive: bool = True
    base_url: str = ""
    username: str = ""
    username_env: str = ""
    scope_type: Literal["space", "page"] | None = None
    space_key: str | None = None
    page_id: str | None = None
    include_children: bool = False
    credential_ref: str = ""
    access_token_env: str = ""
    refresh_token_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    token_uri_env: str = ""
    api_token_env: str = ""

    @field_validator("page_id", mode="before")
    @classmethod
    def _normalize_page_id(cls, value: object) -> object:
        if isinstance(value, int):
            return str(value)
        return value

    @model_validator(mode="after")
    def _validate_type_fields(self) -> KnowledgeSourceConfig:
        if self.type == "google_drive" and not self.folder_id:
            raise ValueError("google_drive source requires folder_id")
        if self.type == "confluence":
            if not self.base_url:
                raise ValueError("confluence source requires base_url")
            if not self.space_key and not self.page_id:
                raise ValueError("confluence source requires space_key or page_id")
        return self


class KnowledgeBaseConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    tenant_id: str
    name: str = ""
    indexing: KnowledgeIndexingConfig = Field(default_factory=KnowledgeIndexingConfig)
    sources: list[KnowledgeSourceConfig] = Field(default_factory=list)
    sync: KnowledgeSyncConfig = Field(default_factory=KnowledgeSyncConfig)


class KnowledgeConfigSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    knowledge_bases: list[KnowledgeBaseConfig] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_sources(self) -> KnowledgeConfigSnapshot:
        seen: set[str] = set()
        normalized_bases: list[KnowledgeBaseConfig] = []
        for kb in self.knowledge_bases:
            normalized_sources: list[KnowledgeSourceConfig] = []
            for source in kb.sources:
                if source.id in seen:
                    raise ValueError(f"duplicate source id: {source.id}")
                seen.add(source.id)
                normalized_sources.append(
                    source.model_copy(update={"tenant_id": kb.tenant_id, "kb_id": kb.id})
                )
            normalized_bases.append(kb.model_copy(update={"sources": normalized_sources}))
        self.knowledge_bases = normalized_bases
        return self


def knowledge_config_path(base_dir: Path | None = None) -> Path:
    """Return the default Platform config path that contains embedded Knowledge config."""
    if base_dir is not None:
        return base_dir / "platform.yaml"
    return paths.base_dir() / "platform.yaml"


def load_knowledge_config(path: Path | None = None) -> KnowledgeConfigSnapshot:
    """Load and validate embedded Platform Knowledge construction config."""
    config_path = path or knowledge_config_path()
    raw = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{config_path} must contain a mapping")
    knowledge = raw.get("knowledge")
    if isinstance(knowledge, dict):
        raw = {"knowledge_bases": knowledge.get("knowledge_bases", [])}
    _reject_inline_source_secrets(raw, config_path)
    return KnowledgeConfigSnapshot.model_validate(raw)


def _reject_inline_source_secrets(raw: dict[str, object], path: Path) -> None:
    for key, value in flatten(raw):
        if not isinstance(value, str):
            continue
        if key.endswith("_env") or key.endswith("credential_ref"):
            continue
        lowered_key = key.lower()
        secret_key = any(part in lowered_key for part in _SECRET_KEY_PARTS)
        if not secret_key and not looks_inline_secret(value):
            continue
        raise ValueError(
            f"inline secret-like value in knowledge config at '{key}' ({path}); "
            "reference secrets by environment-variable name instead"
        )
