import re
import sys
from collections.abc import Callable
from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from typing import cast

from docx import Document
from openpyxl import load_workbook
from pptx import Presentation
from pypdf import PdfReader

_MARKDOWN_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"
_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


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


_TextParser = Callable[[str, str], ParsedDocument]
_BinaryParser = Callable[[str, bytes], ParsedDocument]


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


def parse_pdf(filename: str, content: bytes) -> ParsedDocument:
    """Parse a text-based PDF into page sections."""

    reader = PdfReader(BytesIO(content))
    if reader.is_encrypted:
        raise ValueError("encrypted PDF is unsupported")

    sections: list[ParsedSection] = []
    warnings: list[str] = []
    for index, page in enumerate(reader.pages, start=1):
        text = _normalize_text(page.extract_text() or "")
        if not text:
            warnings.append("empty_page_skipped")
            continue
        sections.append(
            ParsedSection(
                title=f"Page {index}",
                text=text,
                level=0,
                metadata={"path": f"Page {index}", "page_number": str(index)},
            )
        )

    if not sections:
        raise ValueError("PDF contains no extractable text")

    metadata = {"filename": filename, "format": "pdf", "parser": "pypdf"}
    if warnings:
        metadata["warnings"] = ",".join(sorted(set(warnings)))
    return ParsedDocument(
        filename=filename,
        format="pdf",
        sections=sections,
        metadata=metadata,
    )


def parse_docx(filename: str, content: bytes) -> ParsedDocument:
    """Parse DOCX paragraphs and tables into searchable sections."""

    document = Document(BytesIO(content))
    sections: list[ParsedSection] = []
    current_title = "body"
    current_level = 0
    current_lines: list[str] = []
    heading_stack: list[tuple[int, str]] = []

    def flush_section() -> None:
        normalized_text = _normalize_text("\n".join(current_lines))
        if not normalized_text:
            return
        sections.append(
            ParsedSection(
                title=current_title,
                text=normalized_text,
                level=current_level,
                metadata={"path": _format_heading_path(heading_stack) if heading_stack else "body"},
            )
        )

    for paragraph in document.paragraphs:
        text = _normalize_inline_text(paragraph.text)
        if not text:
            continue
        heading_level = _docx_heading_level(paragraph.style.name if paragraph.style else "")
        if heading_level is not None:
            flush_section()
            current_lines = []
            current_title = text
            current_level = heading_level
            heading_stack = [
                (level, title) for level, title in heading_stack if level < heading_level
            ]
            heading_stack.append((heading_level, text))
            continue
        current_lines.append(text)

    for table in document.tables:
        for row in table.rows:
            cells = [_normalize_inline_text(cell.text) for cell in row.cells]
            row_text = " | ".join(cell for cell in cells if cell)
            if row_text:
                current_lines.append(row_text)

    flush_section()
    if not sections:
        raise ValueError("DOCX contains no extractable text")
    return ParsedDocument(
        filename=filename,
        format="docx",
        sections=sections,
        metadata={"filename": filename, "format": "docx", "parser": "python-docx"},
    )


def parse_pptx(filename: str, content: bytes) -> ParsedDocument:
    """Parse PPTX slide text into searchable sections."""

    presentation = Presentation(BytesIO(content))
    sections: list[ParsedSection] = []
    for index, slide in enumerate(presentation.slides, start=1):
        texts: list[str] = []
        title = ""
        if slide.shapes.title is not None and slide.shapes.title.has_text_frame:
            title = _normalize_inline_text(slide.shapes.title.text)
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue
            text = _normalize_text(shape.text)
            if text:
                texts.append(text)
        section_text = _normalize_text("\n".join(texts))
        if not section_text:
            continue
        section_title = title or f"Slide {index}"
        sections.append(
            ParsedSection(
                title=section_title,
                text=section_text,
                level=0,
                metadata={"path": section_title, "slide_number": str(index)},
            )
        )

    if not sections:
        raise ValueError("PPTX contains no extractable text")
    return ParsedDocument(
        filename=filename,
        format="pptx",
        sections=sections,
        metadata={"filename": filename, "format": "pptx", "parser": "python-pptx"},
    )


def parse_xlsx(filename: str, content: bytes) -> ParsedDocument:
    """Parse XLSX sheet cell text into searchable sections."""

    workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
    sections: list[ParsedSection] = []
    for sheet in workbook.worksheets:
        rows: list[str] = []
        first_row: int | None = None
        last_row: int | None = None
        for row_index, row in enumerate(sheet.iter_rows(values_only=True), start=1):
            cells = [_normalize_inline_text(str(cell)) for cell in row if cell is not None]
            row_text = " | ".join(cell for cell in cells if cell)
            if not row_text:
                continue
            if first_row is None:
                first_row = row_index
            last_row = row_index
            rows.append(row_text)
        section_text = _normalize_text("\n".join(rows))
        if not section_text:
            continue
        metadata = {"path": sheet.title, "sheet_name": sheet.title}
        if first_row is not None and last_row is not None:
            metadata["row_range"] = f"{first_row}-{last_row}"
        sections.append(
            ParsedSection(
                title=sheet.title,
                text=section_text,
                level=0,
                metadata=metadata,
            )
        )

    workbook.close()
    if not sections:
        raise ValueError("XLSX contains no extractable text")
    return ParsedDocument(
        filename=filename,
        format="xlsx",
        sections=sections,
        metadata={"filename": filename, "format": "xlsx", "parser": "openpyxl"},
    )


def parse_document(
    filename: str,
    content: bytes | str,
    mime_type: str | None = None,
) -> ParsedDocument:
    """Dispatch supported source content to the correct knowledge-base parser."""

    parser_name = _parser_name_for(filename, mime_type)
    parser = getattr(sys.modules[__name__], parser_name)
    if parser_name in {"parse_text", "parse_markdown", "parse_html"}:
        text_parser = cast(_TextParser, parser)
        return text_parser(filename, _content_as_text(content))
    binary_parser = cast(_BinaryParser, parser)
    return binary_parser(filename, _content_as_bytes(content))


def _normalize_text(content: str) -> str:
    return "\n".join(line.strip() for line in content.splitlines() if line.strip())


def _parser_name_for(
    filename: str,
    mime_type: str | None,
) -> str:
    suffix = Path(filename).suffix.lower()
    parser_name = _PARSER_BY_SUFFIX.get(suffix)
    if parser_name is not None:
        return parser_name
    normalized_mime = (mime_type or "").lower()
    parser_name = _PARSER_BY_MIME.get(normalized_mime)
    if parser_name is not None:
        return parser_name
    raise ValueError(
        f"unsupported media type for knowledge-base parser: {suffix or normalized_mime}"
    )


def _content_as_text(content: bytes | str) -> str:
    if isinstance(content, str):
        return content
    return content.decode("utf-8")


def _content_as_bytes(content: bytes | str) -> bytes:
    if isinstance(content, bytes):
        return content
    return content.encode("utf-8")


def _docx_heading_level(style_name: str) -> int | None:
    if not style_name.startswith("Heading "):
        return None
    try:
        return int(style_name.removeprefix("Heading "))
    except ValueError:
        return None


def _format_heading_path(heading_stack: list[tuple[int, str]]) -> str:
    return " > ".join(title for _, title in heading_stack)


_PARSER_BY_SUFFIX = {
    ".txt": "parse_text",
    ".md": "parse_markdown",
    ".markdown": "parse_markdown",
    ".html": "parse_html",
    ".htm": "parse_html",
    ".pdf": "parse_pdf",
    ".docx": "parse_docx",
    ".pptx": "parse_pptx",
    ".xlsx": "parse_xlsx",
}
_PARSER_BY_MIME = {
    "text/plain": "parse_text",
    "text/markdown": "parse_markdown",
    "text/x-markdown": "parse_markdown",
    "text/html": "parse_html",
    "application/xhtml+xml": "parse_html",
    "application/pdf": "parse_pdf",
    _DOCX_MIME: "parse_docx",
    _PPTX_MIME: "parse_pptx",
    _XLSX_MIME: "parse_xlsx",
}


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
