from dataclasses import dataclass

from fleetent.config import VectorStoreSettings


@dataclass(frozen=True)
class SearchResult:
    id: str
    score: float


class InMemoryVectorBackend:
    def __init__(self) -> None:
        self._vectors: dict[str, dict[str, list[float]]] = {}

    async def upsert(self, id: str, vector: list[float], namespace: str) -> None:
        self._vectors.setdefault(namespace, {})[id] = vector

    async def search(
        self, vector: list[float], namespace: str, limit: int = 10
    ) -> list[SearchResult]:
        if limit <= 0:
            return []

        results = [
            SearchResult(id=id, score=_similarity(vector, stored_vector))
            for id, stored_vector in self._vectors.get(namespace, {}).items()
        ]
        return sorted(results, key=lambda result: (-result.score, result.id))[:limit]

    async def delete(self, id: str, namespace: str) -> None:
        self._vectors.get(namespace, {}).pop(id, None)


def _similarity(left: list[float], right: list[float]) -> float:
    score = sum(
        left_value * right_value for left_value, right_value in zip(left, right, strict=True)
    )
    return max(0.0, min(1.0, score))


def create_vector_backend(settings: VectorStoreSettings) -> InMemoryVectorBackend:
    if settings.backend != "memory":
        raise ValueError(
            f"Unsupported vector_store.backend {settings.backend!r}. "
            "Supported vector backends: memory"
        )
    return InMemoryVectorBackend()
