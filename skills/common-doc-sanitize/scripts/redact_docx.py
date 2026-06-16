#!/usr/bin/env python3
"""
DOCX 文档脱敏处理器
用法: python3 redact_docx.py <source_path> <output_path> [custom_rules_json]

custom_rules_json: 可选，JSON 数组，每项为正则字符串，例如 '[\"内部机密\", \"PROJ-\\\\d+\"]'
"""
import os
import re
import sys
import shutil
from docx import Document

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact_rules import build_rules  # noqa: E402

# 价格相关列头关键词，表格中命中这些列头的数据列将对所有数字内容替换为 [金额]
PRICE_HEADERS = {
    '单价', '总价', '价格', '金额', '费用', '小计', '合计金额', '单价（元）', '总价（元）',
    'Unit Price', 'Total Price', 'Amount', 'Price', 'Cost', 'Fee',
    'Subtotal', 'Total Amount', 'Unit Cost', 'Extended Price',
}


def redact_text(text, rules):
    for _name, pattern, _use_group, _block_scoped, replacement in rules:
        if replacement == "keep":
            continue
        label = replacement
        def _replacer(m, lbl=label):
            if m.lastindex:
                return m.group()[:m.start(1) - m.start()] + lbl + m.group()[m.end(1) - m.start():]
            return lbl
        text = re.sub(pattern, _replacer, text, flags=re.IGNORECASE)
    return text


def redact_docx(source, output, custom_rules_json=None):
    rules = build_rules(custom_rules_json)
    shutil.copy(source, output)
    doc = Document(output)
    total_hits = [0]

    def process_paragraph(para):
        if not para.runs:
            return
        full_text = ''.join(run.text for run in para.runs)
        replaced = redact_text(full_text, rules)
        if replaced != full_text:
            total_hits[0] += 1
            para.runs[0].text = replaced
            for run in para.runs[1:]:
                run.text = ''

    for para in doc.paragraphs:
        process_paragraph(para)

    amount_pat = re.compile(r'[\d,]+(?:\.\d+)?')

    for table in doc.tables:
        if not table.rows:
            continue
        price_cols = set()
        header_row = table.rows[0]
        for ci, cell in enumerate(header_row.cells):
            if cell.text.strip() in PRICE_HEADERS:
                price_cols.add(ci)

        for ri, row in enumerate(table.rows):
            for ci, cell in enumerate(row.cells):
                for para in cell.paragraphs:
                    if ri > 0 and ci in price_cols and para.runs:
                        full_text = ''.join(run.text for run in para.runs)
                        replaced = amount_pat.sub('[金额]', full_text)
                        if replaced != full_text:
                            total_hits[0] += 1
                            para.runs[0].text = replaced
                            for run in para.runs[1:]:
                                run.text = ''
                    else:
                        process_paragraph(para)

    doc.save(output)
    print(f"OK: {output} (命中 {total_hits[0]} 处)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 redact_docx.py <source_path> <output_path> [custom_rules_json]")
        sys.exit(1)
    redact_docx(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None)
