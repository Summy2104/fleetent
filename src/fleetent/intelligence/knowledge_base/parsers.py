import re
from dataclasses import dataclass
from html.parser import HTMLParser

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


@dataclass(frozen=True)
class ParsedSection:
    """Normalized section extracted from a source document."""

    title: str
    text: str
    level: int
    metadata: dict[str, str]


@dataclass(frozen=True)
class ParsedDocument:
    """Normalized parser output ready for knowledge-base ingest."""

    filename: str
    format: str
    sections: list[ParsedSection]
    metadata: dict[str, str]


def parse_text(filename: str, content: str) -> ParsedDocument:
    """Parse plain text into a single body section."""

    normalized_content = _normalize_text(content)
    if not normalized_content:
        raise ValueError("content must not be empty")

    return ParsedDocument(
        filename=filename,
        format="text",
        sections=[
            ParsedSection(
                title="body",
                text=normalized_content,
                level=0,
                metadata={"path": "body"},
            )
        ],
        metadata={"filename": filename, "format": "text"},
    )


def parse_markdown(filename: str, content: str) -> ParsedDocument:
    """Parse Markdown into structured sections."""

    sections: list[ParsedSection] = []
    current_title = "body"
    current_level = 0
    current_lines: list[str] = []
    heading_stack: list[tuple[int, str]] = []
    in_fence = False

    def flush_section() -> None:
        normalized_text = _normalize_text("\n".join(current_lines))
        if not normalized_text:
            return
        path = _format_heading_path(heading_stack) if current_level else "body"
        sections.append(
            ParsedSection(
                title=current_title,
                text=normalized_text,
                level=current_level,
                metadata={"path": path},
            )
        )

    for line in content.splitlines():
        stripped = line.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            current_lines.append(line.rstrip())
            continue

        heading_match = _MARKDOWN_HEADING_RE.match(stripped) if not in_fence else None
        if heading_match:
            flush_section()
            current_lines = []
            current_level = len(heading_match.group(1))
            current_title = heading_match.group(2).strip()
            heading_stack = [
                (level, title) for level, title in heading_stack if level < current_level
            ]
            heading_stack.append((current_level, current_title))
            continue

        current_lines.append(line.rstrip())

    flush_section()
    if not sections:
        raise ValueError("content must not be empty")

    return ParsedDocument(
        filename=filename,
        format="markdown",
        sections=sections,
        metadata={"filename": filename, "format": "markdown"},
    )


def parse_html(filename: str, content: str) -> ParsedDocument:
    """Parse lightweight HTML into structured sections."""

    parser = _KnowledgeHTMLParser()
    parser.feed(content)
    parser.close()
    sections = parser.sections
    if not sections:
        raise ValueError("content must not be empty")

    metadata = {"filename": filename, "format": "html"}
    if parser.title:
        metadata["title"] = parser.title
    return ParsedDocument(
        filename=filename,
        format="html",
        sections=sections,
        metadata=metadata,
    )


def _normalize_text(content: str) -> str:
    return "\n".join(line.strip() for line in content.splitlines() if line.strip())


def _format_heading_path(heading_stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in heading_stack)


class _KnowledgeHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.sections: list[ParsedSection] = []
        self.title = ""
        self._current_title = "body"
        self._current_level = 0
        self._current_lines: list[str] = []
        self._heading_stack: list[tuple[int, str]] = []
        self._skip_depth = 0
        self._in_title = False
        self._title_parts: list[str] = []
        self._heading_level: int | None = None
        self._heading_parts: list[str] = []
        self._in_table_row = False
        self._in_table_cell = False
        self._cell_parts: list[str] = []
        self._row_cells: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"}:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if normalized_tag == "title":
            self._in_title = True
            self._title_parts = []
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            self._heading_level = int(normalized_tag[1])
            self._heading_parts = []
            return
        if normalized_tag == "tr":
            self._in_table_row = True
            self._row_cells = []
            return
        if normalized_tag in {"td", "th"} and self._in_table_row:
            self._in_table_cell = True
            self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()
        if normalized_tag in {"script", "style"} and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if normalized_tag == "title":
            self._in_title = False
            self.title = _normalize_inline_text(" ".join(self._title_parts))
            if self.title and self._current_title == "body":
                self._current_title = self.title
            return
        if normalized_tag in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            heading_title = _normalize_inline_text(" ".join(self._heading_parts))
            heading_level = self._heading_level or int(normalized_tag[1])
            self._start_heading_section(heading_title, heading_level)
            self._heading_level = None
            self._heading_parts = []
            return
        if normalized_tag in {"td", "th"} and self._in_table_cell:
            cell = _normalize_inline_text(" ".join(self._cell_parts))
            if cell:
                self._row_cells.append(cell)
            self._in_table_cell = False
            self._cell_parts = []
            return
        if normalized_tag == "tr" and self._in_table_row:
            if self._row_cells:
                self._current_lines.append(" | ".join(self._row_cells))
            self._in_table_row = False
            self._row_cells = []

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self._title_parts.append(data)
            return
        if self._heading_level is not None:
            self._heading_parts.append(data)
            return
        if self._in_table_cell:
            self._cell_parts.append(data)
            return
        normalized_data = _normalize_inline_text(data)
        if normalized_data:
            self._current_lines.append(normalized_data)

    def close(self) -> None:
        super().close()
        self._flush_section()

    def _start_heading_section(self, title: str, level: int) -> None:
        if not title:
            return
        self._flush_section()
        self._current_title = title
        self._current_level = level
        self._current_lines = []
        self._heading_stack = [
            (existing_level, existing_title)
            for existing_level, existing_title in self._heading_stack
            if existing_level < level
        ]
        self._heading_stack.append((level, title))

    def _flush_section(self) -> None:
        normalized_text = _normalize_text("\n".join(self._current_lines))
        if not normalized_text:
            return
        path = (
            _format_heading_path(self._heading_stack)
            if self._current_level
            else self._current_title
        )
        self.sections.append(
            ParsedSection(
                title=self._current_title,
                text=normalized_text,
                level=self._current_level,
                metadata={"path": path},
            )
        )
        self._current_lines = []


def _normalize_inline_text(content: str) -> str:
    return " ".join(content.split())
