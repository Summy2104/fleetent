#!/usr/bin/env python3
"""
PDF 文档脱敏处理器
用法: python3 redact_pdf.py <source_path> <output_path> [custom_rules_json [style]]

custom_rules_json: 可选，JSON 数组，每项为正则字符串，例如 '["内部机密", "PROJ-\\\\d+"]'
style: 可选，打码样式，mask（默认，白底标签）或 block（黑色方块）
"""
import os
import re
import sys
import fitz  # PyMuPDF

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact_rules import build_rules  # noqa: E402


# 仅由标点/空白组成时返回 True（用于判断是否合并相邻匹配）
_PUNCT_ONLY = re.compile(r'^[\s\u0000-\u002F\u003A-\u0040\u005B-\u0060\u007B-\u007E'
                         r'\u00B7\u2014\u2026\u300A\u300B\u300C\u300D\u300E\u300F'
                         r'\u3001\u3002\uFF01\uFF08\uFF09\uFF0C\uFF1A\uFF1B\uFF1F'
                         r'\u2018\u2019\u201C\u201D\u3008-\u3011\u2010-\u2015'
                         r'\uFF3B\uFF3D\uFF5B\uFF5D\u00AB\u00BB]*$')


def _merge_ranges(ranges, full_text):
    """合并仅被标点/空白间隔的相邻匹配区间。label 取第一段。"""
    if not ranges:
        return []
    ranges = sorted(ranges, key=lambda r: r[0])
    merged = [list(ranges[0])]  # [start, end, label]
    for start, end, label in ranges[1:]:
        gap = full_text[merged[-1][1]:start]
        if _PUNCT_ONLY.match(gap):
            merged[-1][1] = end
        else:
            merged.append([start, end, label])
    return [tuple(r) for r in merged]


def _apply_range(page, start, end, char_bboxes, char_sizes, style, label):
    """对 [start, end) 字符范围添加遮盖标注。
    按行分组（同一 y 段）分别标注，每行独立一个矩形。"""
    buckets: dict[int, list] = {}
    for ci in range(start, min(end, len(char_bboxes))):
        cb = char_bboxes[ci]
        key = int(cb[1] / 5)
        buckets.setdefault(key, []).append((ci, cb))

    for is_first, (key, items) in enumerate(sorted(buckets.items())):
        rects = [cb for _, cb in items]
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[2] for r in rects)
        y1 = max(r[3] for r in rects)
        bbox = fitz.Rect(x0, y0, x1 + 2, y1 + 0.5)
        if bbox.is_empty:
            continue
        fontsize = max(6, char_sizes[items[0][0]] * 0.85)

        if style == "block":
            page.add_redact_annot(bbox, fill=(0, 0, 0))
        elif is_first == 0:
            page.add_redact_annot(
                bbox, text=label,
                fontname="china-s", fontsize=fontsize,
                fill=(1, 1, 1), text_color=(0.4, 0.4, 0.4),
            )
        else:
            # 续行：白底无文字（标签只在首行显示）
            page.add_redact_annot(bbox, fill=(1, 1, 1))


def redact_pdf(source, output, custom_rules_json=None, style="mask"):
    rules = build_rules(custom_rules_json)
    doc = fitz.open(source)
    total_hits = 0

    for page in doc:
        blocks = page.get_text("rawdict")["blocks"]

        full_text = ""
        char_bboxes = []
        char_sizes = []
        block_ranges = []

        for b in blocks:
            if b["type"] != 0:
                continue
            block_start = len(full_text)
            for line in b["lines"]:
                for span in line["spans"]:
                    fsize = span.get("size", 10)
                    for ch in span["chars"]:
                        full_text += ch["c"]
                        char_bboxes.append(ch["bbox"])
                        char_sizes.append(fsize)
            block_end = len(full_text)
            if block_end > block_start:
                block_ranges.append((block_start, block_end))

        raw_ranges = []
        for _rule_name, pattern, use_group, block_scoped, replacement in rules:
            if replacement == "keep":
                continue
            if block_scoped:
                regions = [(b_start, full_text[b_start:b_end]) for b_start, b_end in block_ranges]
            else:
                regions = [(0, full_text)]

            for offset, text in regions:
                for m in re.finditer(pattern, text, re.IGNORECASE):
                    if use_group and m.lastindex:
                        start = offset + m.start(1)
                        end = offset + m.end(1)
                    else:
                        start = offset + m.start()
                        end = offset + m.end()
                    if start < end:
                        raw_ranges.append((start, end, replacement))

        merged = _merge_ranges(raw_ranges, full_text)
        total_hits += len(merged)

        for start, end, label in merged:
            _apply_range(page, start, end, char_bboxes, char_sizes, style, label)

        page.apply_redactions()

    doc.save(output)
    doc.close()
    print(f"OK: {output} (命中 {total_hits} 处，合并后）")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 redact_pdf.py <source_path> <output_path> [custom_rules_json [style]]")
        sys.exit(1)
    redact_pdf(
        sys.argv[1], sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else None,
        sys.argv[4] if len(sys.argv) > 4 else "mask",
    )
