import hashlib
import math
from dataclasses import dataclass

from fleetent.config import EmbeddingSettings


@dataclass(frozen=True)
class DeterministicEmbedding:
    dimensions: int = 64

    def __post_init__(self) -> None:
        if self.dimensions <= 0:
            raise ValueError("dimensions must be greater than 0")

    def embed(self, text: str) -> list[float]:
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


def create_embedding_backend(settings: EmbeddingSettings) -> DeterministicEmbedding:
    if settings.backend != "deterministic":
        raise ValueError(
            f"Unsupported embedding.backend {settings.backend!r}. "
            "Supported embedding backends: deterministic"
        )
    return DeterministicEmbedding(dimensions=settings.dimensions)
