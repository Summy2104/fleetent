#!/usr/bin/env python3
"""Parse PPTX/DOCX/XLSX files to structured JSON. Usage: parse_office.py <file_path>"""
import json
import os
import sys

SUPPORTED = {".pptx", ".docx", ".xlsx", ".pdf"}


def parse_pptx(path):
    from pptx import Presentation

    prs = Presentation(path)
    slides = []
    for i, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if shape.has_text_frame:
                for para in shape.text_frame.paragraphs:
                    t = "".join(run.text for run in para.runs).strip()
                    if t:
                        texts.append(t)
            elif shape.has_table:
                for row in shape.table.rows:
                    for cell in row.cells:
                        if cell.text.strip():
                            texts.append(cell.text.strip())
        slides.append({"index": i, "texts": texts})
    return {"format": "pptx", "slide_count": len(prs.slides), "slides": slides}


def parse_docx(path):
    from docx import Document

    doc = Document(path)
    items = []
    for para in doc.paragraphs:
        if para.text.strip():
            items.append({"style": para.style.name, "text": para.text.strip()})
    for table in doc.tables:
        rows = [
            [cell.text.strip() for cell in row.cells]
            for row in table.rows
        ]
        items.append({"type": "table", "rows": rows})
    return {"format": "docx", "paragraphs": items}


def parse_xlsx(path):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    sheets = []
    for ws in wb.worksheets:
        rows = []
        for row in ws.iter_rows(values_only=True):
            if any(cell is not None for cell in row):
                rows.append([str(cell) if cell is not None else "" for cell in row])
        sheets.append({"name": ws.title, "rows": rows})
    return {"format": "xlsx", "sheets": sheets}


def parse_pdf(path):
    import fitz  # PyMuPDF

    doc = fitz.open(path)
    pages = []
    for i, page in enumerate(doc, 1):
        text = page.get_text().strip()
        if not text:
            # 扫描版 PDF，尝试 OCR
            try:
                import pytesseract
                from PIL import Image
                import io
                pix = page.get_pixmap(dpi=150)
                img = Image.open(io.BytesIO(pix.tobytes("png")))
                text = pytesseract.image_to_string(img, lang="chi_sim+eng").strip()
            except Exception:
                text = ""
        texts = [t.strip() for t in text.splitlines() if t.strip()]
        pages.append({"index": i, "texts": texts})
    return {"format": "pdf", "page_count": len(doc), "pages": pages}


def main():
    if len(sys.argv) != 2:
        print("Usage: parse_office.py <file_path>", file=sys.stderr)
        sys.exit(1)

    path = sys.argv[1]

    if not os.path.exists(path):
        print(f"FILE_NOT_FOUND: {path} does not exist", file=sys.stderr)
        sys.exit(1)

    ext = os.path.splitext(path)[1].lower()
    if ext not in SUPPORTED:
        print(
            f"UNSUPPORTED_FORMAT: {ext} is not supported. Supported: .pptx .docx .xlsx",
            file=sys.stderr,
        )
        sys.exit(1)

    parsers = {".pptx": parse_pptx, ".docx": parse_docx, ".xlsx": parse_xlsx, ".pdf": parse_pdf}
    try:
        result = parsers[ext](path)
    except Exception as e:
        print(f"PARSE_ERROR: {e}", file=sys.stderr)
        sys.exit(1)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
