from io import BytesIO

import pytest

from fleetent.intelligence.knowledge_base import (
    parse_document,
    parse_docx,
    parse_html,
    parse_markdown,
    parse_pdf,
    parse_pptx,
    parse_text,
    parse_xlsx,
)


def test_parse_document_dispatches_basic_formats_by_extension_and_mime_type():
    text = parse_document("notes.txt", "Plain note")
    markdown = parse_document("guide", "# Guide\nBody", mime_type="text/markdown")
    html = parse_document("page.unknown", "<h1>Page</h1><p>Body</p>", mime_type="text/html")

    assert text.format == "text"
    assert markdown.format == "markdown"
    assert html.format == "html"


@pytest.mark.parametrize(
    ("filename", "mime_type", "expected_format"),
    [
        ("report.pdf", None, "pdf"),
        ("deck.pptx", None, "pptx"),
        ("book.xlsx", None, "xlsx"),
        ("upload", "application/pdf", "pdf"),
        (
            "upload",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "docx",
        ),
        (
            "upload",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "pptx",
        ),
        (
            "upload",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "xlsx",
        ),
    ],
)
def test_parse_document_dispatches_advanced_formats(
    monkeypatch, filename, mime_type, expected_format
):
    from fleetent.intelligence.knowledge_base import parsers

    def fake_parser(name: str, content: bytes):
        return parsers.ParsedDocument(
            filename=name,
            format=expected_format,
            sections=[
                parsers.ParsedSection(
                    title="body",
                    text=f"{expected_format} text",
                    level=0,
                    metadata={"path": "body"},
                )
            ],
            metadata={"filename": name, "format": expected_format},
        )

    monkeypatch.setattr(parsers, f"parse_{expected_format}", fake_parser)

    parsed = parse_document(filename, b"binary content", mime_type=mime_type)

    assert parsed.format == expected_format


def test_parse_document_unsupported_media_type_fails_without_content():
    with pytest.raises(ValueError) as exc_info:
        parse_document("payload.bin", b"secret body token", mime_type="application/octet-stream")

    message = str(exc_info.value)
    assert "unsupported media type" in message
    assert "secret body token" not in message


def test_parse_pdf_pages_become_sections_with_page_metadata(monkeypatch):
    from fleetent.intelligence.knowledge_base import parsers

    class FakePage:
        def __init__(self, text: str | None) -> None:
            self._text = text

        def extract_text(self) -> str | None:
            return self._text

    class FakeReader:
        is_encrypted = False
        pages = [FakePage(" Page one text "), FakePage("  "), FakePage("Page three text")]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setattr(parsers, "PdfReader", FakeReader)

    parsed = parse_pdf("report.pdf", b"%PDF fake")

    assert parsed.format == "pdf"
    assert [(section.title, section.text) for section in parsed.sections] == [
        ("Page 1", "Page one text"),
        ("Page 3", "Page three text"),
    ]
    assert [section.metadata["page_number"] for section in parsed.sections] == ["1", "3"]
    assert parsed.metadata["warnings"] == "empty_page_skipped"


def test_parse_pdf_encrypted_file_fails_without_content(monkeypatch):
    from fleetent.intelligence.knowledge_base import parsers

    class FakeReader:
        is_encrypted = True
        pages = []

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setattr(parsers, "PdfReader", FakeReader)

    with pytest.raises(ValueError) as exc_info:
        parse_pdf("secret.pdf", b"confidential body")

    message = str(exc_info.value)
    assert "encrypted" in message
    assert "confidential body" not in message


def test_parse_pdf_empty_extraction_fails_without_content(monkeypatch):
    from fleetent.intelligence.knowledge_base import parsers

    class FakePage:
        def extract_text(self) -> str:
            return "  "

    class FakeReader:
        is_encrypted = False
        pages = [FakePage()]

        def __init__(self, stream) -> None:
            self.stream = stream

    monkeypatch.setattr(parsers, "PdfReader", FakeReader)

    with pytest.raises(ValueError) as exc_info:
        parse_pdf("scan.pdf", b"image-only body")

    message = str(exc_info.value)
    assert "extractable text" in message
    assert "image-only body" not in message


def test_parse_docx_paragraphs_tables_and_headings_are_searchable():
    from docx import Document

    stream = BytesIO()
    document = Document()
    document.add_heading("Guide", level=1)
    document.add_paragraph("Install the agent")
    document.add_heading("Owners", level=2)
    table = document.add_table(rows=2, cols=2)
    table.rows[0].cells[0].text = "Name"
    table.rows[0].cells[1].text = "Owner"
    table.rows[1].cells[0].text = "Fleetent"
    table.rows[1].cells[1].text = "Platform"
    document.save(stream)

    parsed = parse_docx("guide.docx", stream.getvalue())

    assert parsed.format == "docx"
    assert [(section.title, section.text) for section in parsed.sections] == [
        ("Guide", "Install the agent"),
        ("Owners", "Name | Owner\nFleetent | Platform"),
    ]
    assert [section.metadata["path"] for section in parsed.sections] == [
        "Guide",
        "Guide > Owners",
    ]


def test_parse_pptx_slides_become_sections_with_slide_metadata():
    from pptx import Presentation

    stream = BytesIO()
    presentation = Presentation()
    title_layout = presentation.slide_layouts[0]
    title_slide = presentation.slides.add_slide(title_layout)
    title_slide.shapes.title.text = "Pilot Deck"
    title_slide.placeholders[1].text = "Launch checklist"
    blank_layout = presentation.slide_layouts[6]
    body_slide = presentation.slides.add_slide(blank_layout)
    textbox = body_slide.shapes.add_textbox(0, 0, 100, 100)
    textbox.text = "Second slide body"
    presentation.save(stream)

    parsed = parse_pptx("deck.pptx", stream.getvalue())

    assert parsed.format == "pptx"
    assert [(section.title, section.text) for section in parsed.sections] == [
        ("Pilot Deck", "Pilot Deck\nLaunch checklist"),
        ("Slide 2", "Second slide body"),
    ]
    assert [section.metadata["slide_number"] for section in parsed.sections] == ["1", "2"]


def test_parse_xlsx_sheets_become_sections_with_sheet_metadata():
    from openpyxl import Workbook

    stream = BytesIO()
    workbook = Workbook()
    active = workbook.active
    active.title = "Runbook"
    active.append(["Name", "Owner"])
    active.append(["Fleetent", "Platform"])
    empty = workbook.create_sheet("Empty")
    empty["A1"] = None
    second = workbook.create_sheet("Metrics")
    second.append(["Metric", "Value"])
    second.append(["Latency", 42])
    workbook.save(stream)

    parsed = parse_xlsx("book.xlsx", stream.getvalue())

    assert parsed.format == "xlsx"
    assert [(section.title, section.text) for section in parsed.sections] == [
        ("Runbook", "Name | Owner\nFleetent | Platform"),
        ("Metrics", "Metric | Value\nLatency | 42"),
    ]
    assert [section.metadata["sheet_name"] for section in parsed.sections] == [
        "Runbook",
        "Metrics",
    ]


def test_parse_text_filters_empty_lines_and_creates_body_section():
    parsed = parse_text("notes.txt", "  first line\n\n\t \nsecond line  ")

    assert len(parsed.sections) == 1
    assert parsed.sections[0].title == "body"
    assert parsed.sections[0].text == "first line\nsecond line"
    assert parsed.sections[0].level == 0
    assert parsed.sections[0].metadata == {"path": "body"}


@pytest.mark.parametrize("content", ["", " \n\t  "])
def test_parse_text_rejects_empty_content(content):
    with pytest.raises(ValueError, match="content must not be empty"):
        parse_text("empty.txt", content)


def test_parse_markdown_headings_create_section_title_path_and_level():
    parsed = parse_markdown(
        "guide.md",
        "# Guide\nIntro\n\n## Install\nRun setup\n\n### Verify\nCheck status",
    )

    assert [(section.title, section.level, section.text) for section in parsed.sections] == [
        ("Guide", 1, "Intro"),
        ("Install", 2, "Run setup"),
        ("Verify", 3, "Check status"),
    ]
    assert [section.metadata["path"] for section in parsed.sections] == [
        "Guide",
        "Guide > Install",
        "Guide > Install > Verify",
    ]


def test_parse_markdown_preserves_fenced_code_block_hashes():
    parsed = parse_markdown(
        "guide.md",
        "# Guide\n```markdown\n# Not a heading\n```\nAfter code",
    )

    assert len(parsed.sections) == 1
    assert parsed.sections[0].text == "```markdown\n# Not a heading\n```\nAfter code"


def test_parse_markdown_filters_empty_sections():
    parsed = parse_markdown("guide.md", "# Empty\n\n## Filled\nContent")

    assert [(section.title, section.text) for section in parsed.sections] == [("Filled", "Content")]


def test_parse_html_ignores_script_and_style_content():
    parsed = parse_html(
        "page.html",
        """
        <html>
          <head><style>.hidden { color: red; }</style></head>
          <body><script>alert('x')</script><h1>Guide</h1><p>Visible text</p></body>
        </html>
        """,
    )

    all_text = "\n".join(section.text for section in parsed.sections)
    assert "Visible text" in all_text
    assert "alert" not in all_text
    assert "hidden" not in all_text


def test_parse_html_extracts_title_headings_and_body_text():
    parsed = parse_html(
        "page.html",
        "<html><head><title>Handbook</title></head><body><p>Intro</p><h1>Setup</h1>"
        "<p>Install agent</p><h2>Verify</h2><p>Check status</p></body></html>",
    )

    assert parsed.metadata["title"] == "Handbook"
    assert [(section.title, section.level, section.text) for section in parsed.sections] == [
        ("Handbook", 0, "Intro"),
        ("Setup", 1, "Install agent"),
        ("Verify", 2, "Check status"),
    ]
    assert [section.metadata["path"] for section in parsed.sections] == [
        "Handbook",
        "Setup",
        "Setup > Verify",
    ]


def test_parse_html_converts_simple_tables_to_searchable_text():
    parsed = parse_html(
        "page.html",
        "<table><tr><th>Name</th><th>Owner</th></tr><tr><td>Fleetent</td>"
        "<td>Platform</td></tr></table>",
    )

    assert parsed.sections[0].text == "Name | Owner\nFleetent | Platform"
