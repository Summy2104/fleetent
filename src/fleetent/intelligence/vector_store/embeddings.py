import hashlib
import math
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from fleetent.config import EmbeddingSettings
from fleetent.model import ModelConfigError, ModelPolicySnapshot


class EmbeddingProvider(Protocol):
    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector for text."""


class EmbeddingProviderError(RuntimeError):
    """Raised when an embedding provider cannot return a valid vector."""


@dataclass(frozen=True)
class DeterministicEmbeddingProvider:
    dimensions: int = 64

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be greater than 0")

    async def embed(self, text: str) -> list[float]:
        """Return a stable normalized vector for local development and tests."""
        if not text.strip():
            return [0.0] * self.dimensions

        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=16).digest()
            index = int.from_bytes(digest[:8], byteorder="big") % self.dimensions
            weight = 1.0 if digest[8] % 2 == 0 else -1.0
            vector[index] += weight

        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0.0:
            return vector
        return [value / norm for value in vector]


@dataclass(frozen=True)
class HttpEmbeddingProvider:
    endpoint: str
    model: str
    dimensions: int
    api_key_env: str = ""
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be greater than 0")
        if not self.endpoint.strip():
            raise ValueError("embedding.endpoint must not be empty for http backend")

    async def embed(self, text: str) -> list[float]:
        """Return an embedding vector from an OpenAI-style HTTP endpoint."""
        if not text.strip():
            return [0.0] * self.dimensions

        headers = _authorization_header(self.api_key_env)
        payload = {"model": self.model, "input": [text], "dimensions": self.dimensions}
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(self.endpoint, json=payload, headers=headers)
        except httpx.TimeoutException as exc:
            raise EmbeddingProviderError("HTTP embedding request timed out") from exc
        except httpx.HTTPError as exc:
            raise EmbeddingProviderError(f"HTTP embedding request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            raise EmbeddingProviderError(
                f"HTTP embedding provider returned status {response.status_code}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise EmbeddingProviderError("HTTP embedding provider returned malformed JSON") from exc

        embedding = _extract_embedding(body)
        if len(embedding) != self.dimensions:
            message = (
                f"HTTP embedding dimension mismatch: expected {self.dimensions}, "
                f"got {len(embedding)}"
            )
            raise EmbeddingProviderError(message)
        return embedding


DeterministicEmbedding = DeterministicEmbeddingProvider


def create_embedding_provider(settings: EmbeddingSettings) -> EmbeddingProvider:
    if settings.backend == "deterministic":
        return DeterministicEmbeddingProvider(dimensions=settings.dimensions)
    if settings.backend == "http":
        return HttpEmbeddingProvider(
            endpoint=_resolve_env_value(settings.endpoint, settings.endpoint_env),
            model=_resolve_env_value(settings.model, settings.model_env),
            dimensions=_resolve_dimensions(settings.dimensions, settings.dimensions_env),
            api_key_env=settings.api_key_env,
            timeout_seconds=settings.timeout_seconds,
        )
    raise ValueError(
        f"Unsupported embedding.backend {settings.backend!r}. "
        "Supported embedding backends: deterministic, http"
    )


def create_embedding_backend(settings: EmbeddingSettings) -> EmbeddingProvider:
    return create_embedding_provider(settings)


def create_embedding_provider_from_policy(policy: ModelPolicySnapshot) -> EmbeddingProvider:
    resolved = policy.resolve("embedding")[0]
    if resolved.protocol != "http_embedding":
        raise ModelConfigError(
            f"embedding target '{resolved.target_id}' uses unsupported protocol "
            f"{resolved.protocol!r}"
        )
    if not resolved.endpoint:
        raise ModelConfigError(f"embedding target '{resolved.target_id}' missing endpoint")
    dimensions = _int_param(resolved.params, "dimensions", 64)
    timeout = _float_param(resolved.params, "timeout_seconds", 10.0)
    return HttpEmbeddingProvider(
        endpoint=resolved.endpoint,
        model=resolved.model or "",
        dimensions=dimensions,
        api_key_env=resolved.api_key_env or "",
        timeout_seconds=timeout,
    )


def _int_param(params: dict[str, object], key: str, default: int) -> int:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ModelConfigError(f"embedding param '{key}' must be an integer")
    return value


def _float_param(params: dict[str, object], key: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ModelConfigError(f"embedding param '{key}' must be numeric")
    return float(value)


def _authorization_header(api_key_env: str) -> dict[str, str]:
    if not api_key_env:
        return {}
    api_key = os.environ.get(api_key_env)
    if not api_key:
        return {}
    return {"Authorization": f"Bearer {api_key}"}


def _resolve_env_value(value: str, env_name: str) -> str:
    if env_name:
        return os.environ.get(env_name, value)
    return value


def _resolve_dimensions(value: int, env_name: str) -> int:
    if not env_name:
        return value
    raw_value = os.environ.get(env_name)
    if raw_value is None or raw_value == "":
        return value
    try:
        return int(raw_value)
    except ValueError as exc:
        raise ValueError(f"embedding dimensions env var {env_name} must be an integer") from exc


def _extract_embedding(body: object) -> list[float]:
    if not isinstance(body, dict):
        raise EmbeddingProviderError("HTTP embedding provider response missing embedding")

    data = body.get("data")
    if not isinstance(data, list) or not data:
        raise EmbeddingProviderError("HTTP embedding provider response missing embedding")

    first = data[0]
    if not isinstance(first, dict):
        raise EmbeddingProviderError("HTTP embedding provider response missing embedding")

    embedding = first.get("embedding")
    if not isinstance(embedding, list):
        raise EmbeddingProviderError("HTTP embedding provider response missing embedding")
    if not all(isinstance(value, int | float) for value in embedding):
        raise EmbeddingProviderError("HTTP embedding provider response contains non-numeric values")
    return [float(value) for value in embedding]
