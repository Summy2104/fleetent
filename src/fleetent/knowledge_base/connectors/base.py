from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class DocumentRef:
    """Document identity and location returned by a knowledge-base connector."""

    id: str
    filename: str
    format: str
    path: str | None = None
    url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


class DataSource(Protocol):
    """Connector boundary for listing and fetching source documents."""

    def list_documents(self) -> list[DocumentRef]:
        """Return documents available from this source."""

    def fetch(self, ref: DocumentRef) -> bytes:
        """Return raw source content for a document ref."""
