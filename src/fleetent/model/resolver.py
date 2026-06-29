"""Agent-scoped model policy resolver."""

import os
from collections.abc import Awaitable, Callable

from pydantic import BaseModel, ConfigDict

from fleetent.agent_config import AgentFile, AgentModels

STANDARD_ROUTE_KEYS = frozenset(
    {
        "default",
        "memory_extraction",
        "kb_extraction",
        "vision",
        "embedding",
        "rerank",
        "image_generation",
        "audio_transcription",
        "audio_generation",
    }
)


class ModelConfigError(RuntimeError):
    """Raised for invalid model policy or missing deployment configuration."""


class ModelAuthError(RuntimeError):
    """Raised for authentication failures; callers must not fallback."""


class ModelCallSwitchableError(RuntimeError):
    """Raised when a target failure may switch to the next fallback target."""


class ModelTargetSnapshot(BaseModel):
    """Service-readable target metadata without plaintext credentials."""

    model_config = ConfigDict(frozen=True)

    id: str
    provider: str
    protocol: str
    base_url: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    max_tokens: int | None = None
    params: dict[str, object] = {}


class ModelRouteEntrySnapshot(BaseModel):
    """Service-readable route entry metadata."""

    model_config = ConfigDict(frozen=True)

    target: str
    max_tokens: int | None = None
    params: dict[str, object] = {}


class ResolvedModelConfig(BaseModel):
    """Concrete model call config for one route target."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    route_key: str
    target_id: str
    provider: str
    protocol: str
    base_url: str | None = None
    endpoint: str | None = None
    model: str | None = None
    api_key_env: str | None = None
    max_tokens: int | None = None
    params: dict[str, object] = {}


class ModelPolicySnapshot(BaseModel):
    """Validated, cacheable model routing policy for one Agent."""

    model_config = ConfigDict(frozen=True)

    agent_id: str
    targets: dict[str, ModelTargetSnapshot]
    routes: dict[str, tuple[ModelRouteEntrySnapshot, ...]]

    @classmethod
    def from_agent(cls, agent: AgentFile) -> "ModelPolicySnapshot":
        """Build a service-readable policy snapshot from an Agent file."""
        return cls.from_models(agent_id=agent.name, models=agent.models)

    @classmethod
    def from_models(cls, *, agent_id: str, models: AgentModels) -> "ModelPolicySnapshot":
        """Build a snapshot from the parsed ``agent.yaml.models`` section."""
        return cls(
            agent_id=agent_id,
            targets={
                target.id: ModelTargetSnapshot(
                    id=target.id,
                    provider=target.provider,
                    protocol=target.protocol,
                    base_url=target.base_url,
                    endpoint=target.endpoint,
                    model=target.model,
                    api_key_env=target.api_key_env,
                    max_tokens=target.max_tokens,
                    params=dict(target.params),
                )
                for target in models.targets
            },
            routes={
                route: tuple(
                    ModelRouteEntrySnapshot(
                        target=entry.target,
                        max_tokens=entry.max_tokens,
                        params=dict(entry.params),
                    )
                    for entry in entries
                )
                for route, entries in models.routes.items()
            },
        )

    def resolve(self, route_key: str) -> tuple[ResolvedModelConfig, ...]:
        """Resolve one route key to an ordered fallback chain."""
        entries = self.routes.get(route_key)
        if entries is None:
            raise ModelConfigError(f"model route '{route_key}' is not configured")
        resolved: list[ResolvedModelConfig] = []
        for entry in entries:
            target = self.targets.get(entry.target)
            if target is None:
                raise ModelConfigError(
                    f"model route '{route_key}' references unknown target '{entry.target}'"
                )
            resolved.append(_merge(self.agent_id, route_key, target, entry))
        return tuple(resolved)

    def require_api_key(self, resolved: ResolvedModelConfig) -> str | None:
        """Return the configured API key, failing loud if a referenced env is missing."""
        if not resolved.api_key_env:
            return None
        api_key = os.environ.get(resolved.api_key_env)
        if not api_key:
            raise ModelConfigError(
                f"Missing env var {resolved.api_key_env} for model route "
                f"'{resolved.route_key}' target '{resolved.target_id}'"
            )
        return api_key


def _merge(
    agent_id: str,
    route_key: str,
    target: ModelTargetSnapshot,
    entry: ModelRouteEntrySnapshot,
) -> ResolvedModelConfig:
    params = {**target.params, **entry.params}
    return ResolvedModelConfig(
        agent_id=agent_id,
        route_key=route_key,
        target_id=target.id,
        provider=target.provider,
        protocol=target.protocol,
        base_url=target.base_url,
        endpoint=target.endpoint,
        model=target.model,
        api_key_env=target.api_key_env,
        max_tokens=entry.max_tokens if entry.max_tokens is not None else target.max_tokens,
        params=params,
    )


async def call_with_policy[T](
    policy: ModelPolicySnapshot,
    route_key: str,
    caller: Callable[[ResolvedModelConfig], Awaitable[T]],
) -> T:
    """Call a route chain, falling back only on switchable provider failures."""
    last_exc: ModelCallSwitchableError | None = None
    for resolved in policy.resolve(route_key):
        policy.require_api_key(resolved)
        try:
            return await caller(resolved)
        except (ModelConfigError, ModelAuthError):
            raise
        except ModelCallSwitchableError as exc:
            last_exc = exc
            continue
    if last_exc is not None:
        raise last_exc
    raise ModelConfigError(f"model route '{route_key}' has no targets")
