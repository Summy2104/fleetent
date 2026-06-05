import hashlib
import os
from dataclasses import dataclass
from typing import Protocol

import httpx

from fleetent.config import RerankSettings
from fleetent.model import ModelConfigError, ModelPolicySnapshot


@dataclass(frozen=True)
class RerankResult:
    index: int
    score: float


class RerankProvider(Protocol):
    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:
        """Return ranked document indexes and scores."""


class RerankProviderError(RuntimeError):
    """Raised when a rerank provider cannot return valid results."""


class DisabledRerankProvider:
    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:
        """Fail because rerank is intentionally disabled."""
        raise RerankProviderError("Rerank provider is disabled")


class DeterministicRerankProvider:
    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:
        """Return stable scores for tests without external services."""
        limit = len(documents) if top_n is None else max(0, min(top_n, len(documents)))
        scored = [
            RerankResult(index=index, score=_deterministic_score(query, document))
            for index, document in enumerate(documents)
        ]
        return sorted(scored, key=lambda result: (-result.score, result.index))[:limit]


@dataclass(frozen=True)
class HttpRerankProvider:
    endpoint: str
    model: str
    api_key_env: str = ""
    timeout_seconds: float = 10.0

    def __post_init__(self) -> None:
        if not self.endpoint.strip():
            raise ValueError("rerank.endpoint must not be empty for http backend")

    async def rerank(
        self, query: str, documents: list[str], top_n: int | None = None
    ) -> list[RerankResult]:
        """Return rerank results from an HTTP endpoint."""
        payload = {
            "model": self.model,
            "query": query,
            "documents": documents,
            "top_n": top_n,
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    self.endpoint,
                    json=payload,
                    headers=_authorization_header(self.api_key_env),
                )
        except httpx.TimeoutException as exc:
            raise RerankProviderError("HTTP rerank request timed out") from exc
        except httpx.HTTPError as exc:
            raise RerankProviderError(f"HTTP rerank request failed: {exc}") from exc

        if response.status_code < 200 or response.status_code >= 300:
            detail = _error_detail(response)
            suffix = f": {detail}" if detail else ""
            raise RerankProviderError(
                f"HTTP rerank provider returned status {response.status_code}{suffix}"
            )

        try:
            body = response.json()
        except ValueError as exc:
            raise RerankProviderError("HTTP rerank provider returned malformed JSON") from exc

        return _extract_results(body, document_count=len(documents))


def create_rerank_provider(settings: RerankSettings) -> RerankProvider:
    if settings.backend == "disabled":
        return DisabledRerankProvider()
    if settings.backend == "deterministic":
        return DeterministicRerankProvider()
    if settings.backend == "http":
        return HttpRerankProvider(
            endpoint=_resolve_env_value(settings.endpoint, settings.endpoint_env),
            model=_resolve_env_value(settings.model, settings.model_env),
            api_key_env=settings.api_key_env,
            timeout_seconds=settings.timeout_seconds,
        )
    raise ValueError(
        f"Unsupported rerank.backend {settings.backend!r}. "
        "Supported rerank backends: disabled, deterministic, http"
    )


def create_rerank_provider_from_policy(policy: ModelPolicySnapshot) -> RerankProvider:
    resolved = policy.resolve("rerank")[0]
    if resolved.protocol != "http_rerank":
        raise ModelConfigError(
            f"rerank target '{resolved.target_id}' uses unsupported protocol {resolved.protocol!r}"
        )
    if not resolved.endpoint:
        raise ModelConfigError(f"rerank target '{resolved.target_id}' missing endpoint")
    timeout = _float_param(resolved.params, "timeout_seconds", 10.0)
    return HttpRerankProvider(
        endpoint=resolved.endpoint,
        model=resolved.model or "",
        api_key_env=resolved.api_key_env or "",
        timeout_seconds=timeout,
    )


def _float_param(params: dict[str, object], key: str, default: float) -> float:
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ModelConfigError(f"rerank param '{key}' must be numeric")
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


def _error_detail(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return ""
    if not isinstance(body, dict):
        return ""
    error = body.get("error")
    if isinstance(error, str):
        return error
    if isinstance(error, dict):
        message = error.get("message")
        if isinstance(message, str):
            return message
    message = body.get("message")
    return message if isinstance(message, str) else ""


def _deterministic_score(query: str, document: str) -> float:
    query_terms = set(query.lower().split())
    document_terms = set(document.lower().split())
    if query_terms or document_terms:
        overlap = len(query_terms & document_terms)
        union = len(query_terms | document_terms)
        lexical_score = overlap / union if union else 0.0
    else:
        lexical_score = 0.0

    digest = hashlib.blake2b(f"{query}\0{document}".encode(), digest_size=8).digest()
    tie_breaker = int.from_bytes(digest, byteorder="big") / float(2**64)
    return min(1.0, lexical_score + tie_breaker * 0.000001)


def _extract_results(body: object, document_count: int) -> list[RerankResult]:
    if not isinstance(body, dict):
        raise RerankProviderError("HTTP rerank provider response missing results")

    results = body.get("results")
    if not isinstance(results, list):
        raise RerankProviderError("HTTP rerank provider response missing results")

    parsed: list[RerankResult] = []
    for item in results:
        if not isinstance(item, dict):
            raise RerankProviderError("HTTP rerank provider response has invalid result")

        index = item.get("index")
        if not isinstance(index, int):
            raise RerankProviderError("HTTP rerank provider result index is invalid")
        if index < 0 or index >= document_count:
            raise RerankProviderError(f"HTTP rerank provider result index {index} out of range")

        score = item.get("score", item.get("relevance_score"))
        if not isinstance(score, int | float):
            raise RerankProviderError("HTTP rerank provider result score is invalid")

        parsed.append(RerankResult(index=index, score=float(score)))

    return parsed
