"""Tests for parse_office.py — run with: pytest skills/common-office-reader/scripts/test_parse_office.py -v"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = str(Path(__file__).parent / "parse_office.py")


def run(path):
    result = subprocess.run(
        [sys.executable, SCRIPT, path],
        capture_output=True, text=True
    )
    return result


def test_unsupported_format():
    with tempfile.NamedTemporaryFile(suffix=".xls") as f:
        r = run(f.name)
    assert r.returncode == 1
    assert "UNSUPPORTED_FORMAT" in r.stderr


def test_parse_pdf_text():
    """Text-layer PDF: pages with extractable text should be returned."""
    import fitz  # PyMuPDF

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Hello PDF World")
    doc.save(pdf_path)
    doc.close()

    r = run(pdf_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["format"] == "pdf"
    assert data["page_count"] == 1
    assert len(data["pages"]) == 1
    assert any("Hello PDF World" in t for t in data["pages"][0]["texts"])

    Path(pdf_path).unlink(missing_ok=True)


def test_file_not_found():
    r = run("/tmp/does_not_exist_abc123.pptx")
    assert r.returncode == 1
    assert "FILE_NOT_FOUND" in r.stderr


def test_parse_pptx():
    from pptx import Presentation
    from pptx.util import Inches

    with tempfile.NamedTemporaryFile(suffix=".pptx", delete=False) as f:
        pptx_path = f.name

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Test Title"
    slide.placeholders[1].text = "Test Body"
    prs.save(pptx_path)

    r = run(pptx_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["format"] == "pptx"
    assert data["slide_count"] == 1
    assert len(data["slides"]) == 1
    texts = data["slides"][0]["texts"]
    assert any("Test Title" in t for t in texts)
    assert any("Test Body" in t for t in texts)

    Path(pptx_path).unlink(missing_ok=True)


def test_parse_docx():
    from docx import Document

    with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as f:
        docx_path = f.name

    doc = Document()
    doc.add_heading("Chapter One", level=1)
    doc.add_paragraph("First paragraph.")
    table = doc.add_table(rows=2, cols=2)
    table.cell(0, 0).text = "A"
    table.cell(0, 1).text = "B"
    table.cell(1, 0).text = "1"
    table.cell(1, 1).text = "2"
    doc.save(docx_path)

    r = run(docx_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["format"] == "docx"
    paras = data["paragraphs"]
    texts = [p.get("text", "") for p in paras if "text" in p]
    assert any("Chapter One" in t for t in texts)
    assert any("First paragraph" in t for t in texts)
    tables = [p for p in paras if p.get("type") == "table"]
    assert len(tables) == 1
    assert tables[0]["rows"][0] == ["A", "B"]

    Path(docx_path).unlink(missing_ok=True)


def test_parse_xlsx():
    import openpyxl

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as f:
        xlsx_path = f.name

    wb = openpyxl.Workbook()
    ws1 = wb.active
    ws1.title = "Sales"
    ws1.append(["Month", "Revenue"])
    ws1.append(["Jan", "100"])
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Total", "100"])
    wb.save(xlsx_path)

    r = run(xlsx_path)
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["format"] == "xlsx"
    assert len(data["sheets"]) == 2
    assert data["sheets"][0]["name"] == "Sales"
    assert data["sheets"][0]["rows"][0] == ["Month", "Revenue"]
    assert data["sheets"][1]["name"] == "Summary"

    Path(xlsx_path).unlink(missing_ok=True)
