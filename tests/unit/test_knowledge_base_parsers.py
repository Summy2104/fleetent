import pytest

from fleetent.intelligence.knowledge_base import parse_html, parse_markdown, parse_text


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
