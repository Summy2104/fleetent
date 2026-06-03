from pathlib import Path

from fleetent.intelligence.knowledge_base.connectors.base import DocumentRef

_FORMAT_BY_SUFFIX = {
    ".txt": "text",
    ".md": "markdown",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
}


class LocalDirectoryDataSource:
    """Data source that lists supported files from an explicitly allowlisted root."""

    def __init__(self, root_path: str | Path, allowed_roots: list[str | Path]) -> None:
        if not allowed_roots:
            raise ValueError("local directory source requires at least one allowlisted root")
        self._allowed_roots = [Path(root).expanduser().resolve() for root in allowed_roots]
        self._root_path = Path(root_path).expanduser().resolve()
        if not self._is_under_allowed_root(self._root_path):
            raise ValueError("local directory source root must be under an allowlisted root")
        if not self._root_path.is_dir():
            raise ValueError("local directory source root must be an existing directory")

    def list_documents(self) -> list[DocumentRef]:
        """Return supported local files under the configured root."""

        refs: list[DocumentRef] = []
        for path in self._iter_files():
            document_format = _FORMAT_BY_SUFFIX.get(path.suffix.lower())
            if document_format is None:
                continue
            relative_path = path.relative_to(self._root_path).as_posix()
            refs.append(
                DocumentRef(
                    id=f"local:{relative_path}",
                    filename=path.name,
                    format=document_format,
                    path=str(path),
                    metadata={
                        "source_path": str(path),
                        "relative_path": relative_path,
                    },
                )
            )
        return refs

    def fetch(self, ref: DocumentRef) -> bytes:
        """Read raw bytes for a document ref after validating its path."""

        if ref.path is None:
            raise ValueError("local document ref must include path")
        path = Path(ref.path).expanduser().resolve()
        self._ensure_under_root(path)
        return path.read_bytes()

    def count_unsupported_documents(self) -> int:
        """Return unsupported file count under root for sync summaries."""

        return sum(1 for path in self._iter_files() if path.suffix.lower() not in _FORMAT_BY_SUFFIX)

    def _iter_files(self) -> list[Path]:
        paths: list[Path] = []
        for path in self._root_path.rglob("*"):
            if not path.is_file():
                continue
            resolved_path = path.resolve()
            if self._is_under_root(resolved_path):
                paths.append(resolved_path)
        return sorted(paths, key=lambda item: item.relative_to(self._root_path).as_posix())

    def _ensure_under_root(self, path: Path) -> None:
        if not self._is_under_root(path) or not self._is_under_allowed_root(path):
            raise ValueError("local document path must stay under an allowlisted root")

    def _is_under_root(self, path: Path) -> bool:
        return path == self._root_path or path.is_relative_to(self._root_path)

    def _is_under_allowed_root(self, path: Path) -> bool:
        return any(path == root or path.is_relative_to(root) for root in self._allowed_roots)
