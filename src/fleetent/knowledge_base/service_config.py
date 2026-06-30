from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from fleetent.agent_config import AgentFile, ModelRouteEntry, ModelTarget, default_models
from fleetent.config import EmbeddingSettings
from fleetent.knowledge_base.config import KnowledgeConfigSnapshot
from fleetent.secret_scan import flatten, looks_inline_secret

_SECRET_KEY_PARTS = ("token", "secret", "password", "api_key", "credential")


class KBServiceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    service_key_ref: str
    host: str = "127.0.0.1"
    port: int = 8787


class KBDataSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    home: str


class KBRetrievalSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_mode: Literal["vector", "keyword", "hybrid"] = "hybrid"
    top_k: int = 10


class KBEmbeddingSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    endpoint: str = ""
    model: str = ""
    dimensions: int = 0
    api_key_env: str = ""


class KBExtractionSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    endpoint: str = ""
    model: str = ""
    api_key_env: str = ""


class KBChunkingSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_size: int = 1000
    chunk_overlap: int = 200


class KBConnectorSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    type: Literal["google_drive", "confluence"]
    enabled: bool = True
    kb_id: str
    credential_ref: str = ""
    sync_interval_seconds: int | None = None
    folder_id: str = ""
    recursive: bool = True
    base_url: str = ""
    username: str = ""
    username_env: str = ""
    scope_type: Literal["space", "page"] | None = None
    space_key: str | None = None
    page_id: str | None = None
    include_children: bool = False
    access_token_env: str = ""
    refresh_token_env: str = ""
    client_id_env: str = ""
    client_secret_env: str = ""
    token_uri_env: str = ""
    api_token_env: str = ""


class KBServiceConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service: KBServiceSection
    data: KBDataSection
    retrieval: KBRetrievalSection = Field(default_factory=KBRetrievalSection)
    embedding: KBEmbeddingSection = Field(default_factory=KBEmbeddingSection)
    extraction: KBExtractionSection = Field(default_factory=KBExtractionSection)
    chunking: KBChunkingSection = Field(default_factory=KBChunkingSection)
    connectors: list[KBConnectorSection] = Field(default_factory=list)

    def data_dir(self) -> Path:
        return Path(self.data.home).expanduser().resolve()

    def queue_database_url(self) -> str:
        return f"sqlite:///{self.data_dir() / 'kb_ingest_queue.db'}"

    def embedding_settings(self) -> EmbeddingSettings:
        if not self.embedding.endpoint.strip():
            return EmbeddingSettings(
                backend="deterministic", dimensions=max(self.embedding.dimensions, 64)
            )
        return EmbeddingSettings(
            backend="http",
            endpoint=self.embedding.endpoint,
            model=self.embedding.model,
            dimensions=self.embedding.dimensions,
            api_key_env=self.embedding.api_key_env,
        )

    def standalone_agent(self) -> AgentFile:
        models = default_models()
        models.targets = [target for target in models.targets if target.id != "embedding"]
        models.targets.append(
            ModelTarget(
                id="embedding",
                provider="kb-service",
                protocol="http_embedding",
                endpoint=self.embedding.endpoint,
                model=self.embedding.model,
                api_key_env=self.embedding.api_key_env or None,
                params={"dimensions": self.embedding.dimensions},
            )
        )
        models.routes["embedding"] = [ModelRouteEntry(target="embedding")]
        if (
            self.extraction.enabled
            and self.extraction.endpoint.strip()
            and self.extraction.model.strip()
        ):
            models.targets.append(
                ModelTarget(
                    id="kb-extraction",
                    provider="kb-service",
                    protocol="openai_chat",
                    base_url=self.extraction.endpoint,
                    model=self.extraction.model,
                    api_key_env=self.extraction.api_key_env or None,
                )
            )
            models.routes["kb_extraction"] = [ModelRouteEntry(target="kb-extraction")]
        return AgentFile(name="kb-service-standalone", version=1, models=models)

    def configure_process_runtime(self) -> None:
        from fleetent import agent_config, vector_store

        agent_config.set_default_agent_for_process(self.standalone_agent())
        vector_store.configure_from_active_agent()

    def connector_rows(self) -> list[dict[str, object]]:
        rows: list[dict[str, object]] = []
        for connector in self.connectors:
            rows.append(
                {
                    "connector_id": connector.id,
                    "kind": connector.type,
                    "tenant_id": self.service.tenant_id,
                    "kb_id": connector.kb_id,
                    "enabled": connector.enabled,
                    "sync_interval_seconds": connector.sync_interval_seconds,
                    "config": {
                        "folder_id": connector.folder_id,
                        "recursive": connector.recursive,
                        "base_url": connector.base_url,
                        "username": connector.username,
                        "username_env": connector.username_env,
                        "scope_type": connector.scope_type,
                        "space_key": connector.space_key,
                        "page_id": connector.page_id,
                        "include_children": connector.include_children,
                        "credential_ref": connector.credential_ref,
                        "access_token_env": connector.access_token_env,
                        "refresh_token_env": connector.refresh_token_env,
                        "client_id_env": connector.client_id_env,
                        "client_secret_env": connector.client_secret_env,
                        "token_uri_env": connector.token_uri_env,
                        "api_token_env": connector.api_token_env,
                    },
                }
            )
        return rows

    def connector_settings(self) -> KnowledgeConfigSnapshot:
        knowledge_bases: dict[str, dict[str, object]] = {}
        for row in self.connector_rows():
            config = dict(row["config"])
            kb = knowledge_bases.setdefault(
                str(row["kb_id"]),
                {
                    "id": str(row["kb_id"]),
                    "tenant_id": self.service.tenant_id,
                    "indexing": {
                        "chunk_size": self.chunking.chunk_size,
                        "chunk_overlap": self.chunking.chunk_overlap,
                    },
                    "sources": [],
                },
            )
            kb["sources"].append(
                {
                    "id": str(row["connector_id"]),
                    "type": str(row["kind"]),
                    "enabled": bool(row["enabled"]),
                    "folder_id": config.get("folder_id", ""),
                    "recursive": bool(config.get("recursive", True)),
                    "base_url": config.get("base_url", ""),
                    "username": config.get("username", ""),
                    "username_env": config.get("username_env", ""),
                    "scope_type": config.get("scope_type"),
                    "space_key": config.get("space_key"),
                    "page_id": config.get("page_id"),
                    "include_children": bool(config.get("include_children", False)),
                    "credential_ref": config.get("credential_ref", ""),
                    "access_token_env": config.get("access_token_env", ""),
                    "refresh_token_env": config.get("refresh_token_env", ""),
                    "client_id_env": config.get("client_id_env", ""),
                    "client_secret_env": config.get("client_secret_env", ""),
                    "token_uri_env": config.get("token_uri_env", ""),
                    "api_token_env": config.get("api_token_env", ""),
                }
            )
        return KnowledgeConfigSnapshot.model_validate(
            {"knowledge_bases": list(knowledge_bases.values())}
        )


def load_kb_service_config(path: Path) -> KBServiceConfig:
    env_path = path.parent / ".env"
    if env_path.exists():
        from dotenv import load_dotenv

        load_dotenv(env_path, override=False)
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError(f"{path} must contain a mapping")
    _reject_inline_secrets(raw, path)
    config = KBServiceConfig.model_validate(raw)
    data_home = Path(config.data.home).expanduser()
    if not data_home.is_absolute():
        config.data.home = str((path.parent / data_home).resolve())
    return config


def validate_kb_service_boot(config: KBServiceConfig) -> None:
    if not config.embedding.endpoint.strip():
        raise ValueError("embedding endpoint is required for standalone KB service")
    from fleetent.knowledge_base.operations import _read_credential_ref

    missing: list[str] = []
    for connector in config.connectors:
        credential_ref = connector.credential_ref.strip()
        if not credential_ref:
            continue
        try:
            payload = _read_credential_ref(credential_ref)
        except (FileNotFoundError, KeyError):
            missing.append(credential_ref.removeprefix("env:"))
            continue
        if not payload.strip():
            missing.append(credential_ref)
    for env_name in (
        config.embedding.api_key_env.strip(),
        config.extraction.api_key_env.strip(),
    ):
        if env_name and not os.environ.get(env_name):
            missing.append(env_name)
    if missing:
        raise ValueError("missing standalone KB secrets: " + ", ".join(sorted(missing)))


def _reject_inline_secrets(raw: dict[str, object], path: Path) -> None:
    for key, value in flatten(raw):
        if not isinstance(value, str):
            continue
        if (
            key.endswith("_env")
            or key.endswith("credential_ref")
            or key.endswith("service_key_ref")
        ):
            continue
        lowered_key = key.lower()
        secret_key = any(part in lowered_key for part in _SECRET_KEY_PARTS)
        if not secret_key and not looks_inline_secret(value):
            continue
        raise ValueError(
            f"inline secret-like value in standalone kb config at '{key}' ({path}); "
            "reference secrets by env/file ref instead"
        )
