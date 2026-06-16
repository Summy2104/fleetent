#!/usr/bin/env python3
"""
图片文档脱敏处理器（OCR + 矩形遮盖）
用法: python3 redact_image.py <source_path> <output_path> [custom_rules_json [style]]

支持格式: jpg, jpeg, png
依赖: pytesseract, Pillow, tesseract（含 chi_sim 语言包）
custom_rules_json: 可选，JSON 数组，每项为正则字符串
style: 可选，打码样式，mask（默认，白底***）或 block（黑色方块）
"""
import os
import re
import sys
import pytesseract
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from redact_rules import build_patterns  # noqa: E402


def _draw_redact(draw, x, y, w, h, style, font):
    if style == "block":
        draw.rectangle([x, y, x + w, y + h], fill='black')
    else:
        draw.rectangle([x, y, x + w, y + h], fill='white', outline='#cccccc')
        draw.text((x + 2, y + (h - 14) // 2), "**********", fill='black', font=font)


def redact_image(source, output, custom_rules_json=None, style="mask"):
    patterns = build_patterns(custom_rules_json)
    img = Image.open(source)
    draw = ImageDraw.Draw(img)

    # 尝试加载默认字体，失败时退回 Pillow 内置字体
    try:
        font = ImageFont.load_default(size=14)
    except TypeError:
        font = ImageFont.load_default()

    data = pytesseract.image_to_data(
        img, lang='chi_sim+eng', output_type=pytesseract.Output.DICT
    )

    n = len(data['text'])
    total_hits = 0
    covered = set()  # 已处理的 word 索引

    FLAGS = re.IGNORECASE  # OCR 常把大写字母读成小写，统一忽略大小写

    def _apply_pattern_on(text, ctw):
        nonlocal total_hits
        for pattern in patterns:
            for m in re.finditer(pattern, text, FLAGS):
                s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
                hit_words = set(ctw[s:e])
                hit_words -= covered
                if not hit_words:
                    continue
                xs = [data['left'][i] for i in hit_words]
                ys = [data['top'][i] for i in hit_words]
                x2s = [data['left'][i] + data['width'][i] for i in hit_words]
                y2s = [data['top'][i] + data['height'][i] for i in hit_words]
                x0, y0 = min(xs), min(ys)
                w0 = max(x2s) - x0
                h0 = max(y2s) - y0
                _draw_redact(draw, x0, y0, w0, h0, style, font)
                total_hits += 1
                covered.update(hit_words)

    # ── 第一遍：逐词匹配（单词即可命中的模式）──────────────────────────
    for i in range(n):
        word = data['text'][i].strip()
        if not word:
            continue
        for pattern in patterns:
            if re.search(pattern, word, FLAGS):
                x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                _draw_redact(draw, x, y, w, h, style, font)
                total_hits += 1
                covered.add(i)
                break

    # ── 第二遍：按行拼接后匹配（手机号/身份证等被 OCR 切词的场景）──────
    # 将同一行（block_num+par_num+line_num 相同）的词拼成整行，记录每词偏移
    lines: dict = {}
    for i in range(n):
        word = data['text'][i].strip()
        if not word:
            continue
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        lines.setdefault(key, []).append(i)

    for key, indices in lines.items():
        # 拼接行文本，记录每个字符对应的词索引
        line_text = ""
        char_to_word = []
        for idx in indices:
            word = data['text'][idx].strip()
            for _ in word:
                char_to_word.append(idx)
            line_text += word
            # 词间插一个空格以保持连续性
            char_to_word.append(idx)
            line_text += " "

        # 紧凑版（去除所有空格），用于中文多词拼接被空格截断的场景
        line_text_compact = line_text.replace(' ', '')
        char_to_word_compact = [c for c, ch in zip(char_to_word, line_text) if ch != ' ']

        # 第一轮：原始行文本（保留空格，适配英文/数字模式）
        _apply_pattern_on(line_text, char_to_word)
        # 第二轮：紧凑行文本（去除空格，适配中文公司名/姓名/地址被拆词场景）
        _apply_pattern_on(line_text_compact, char_to_word_compact)

    # ── 第三遍：全页合并扫描（兜底 OCR 跨 block 切割场景）──────────────
    # 社会信用代码、银行账号等可能被 OCR 分配到不同 block，行拼接无效；
    # 全页紧凑合并可捕获这类情况，但仅对「长数字/字母编码」类模式生效，
    # 避免跨 block 拼接产生中文误匹配。
    PAGE_WIDE_PATTERNS = [
        r'(?<![A-Z0-9a-z])[0-9A-Za-z]{17,19}(?![A-Z0-9a-z])',  # 社会信用代码（±1 容错）
        r'(?:统一)?社会信用代码\s*[：:]\s*([0-9A-Za-z][0-9A-Za-z\s]{6,22}[0-9A-Za-z])',  # 社会信用代码（标签锚点）
        r'(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)',                       # SSN
        r'(?<!\d)\d{2}-\d{7}(?!\d)',                              # EIN
        r'6\d{15,18}',                                            # 银行卡
        r'(?:银行账号|账号|卡号)[：:]\s*([\d\s\-]{10,30})',         # 银行账号标签
        r'(?:IBAN)\s*[:\-]?\s*([A-Z]{2}\d{2}[A-Z0-9]{11,30})',    # IBAN
    ]
    page_text = ""
    page_char_to_word = []
    for i in range(n):
        word = data['text'][i].strip()
        if not word:
            continue
        for _ in word:
            page_char_to_word.append(i)
        page_text += word
        page_char_to_word.append(i)  # 词间空格
        page_text += " "
    page_text_compact = page_text.replace(' ', '')
    page_char_to_word_compact = [c for c, ch in zip(page_char_to_word, page_text) if ch != ' ']
    for pattern in PAGE_WIDE_PATTERNS:
        for m in re.finditer(pattern, page_text_compact, FLAGS):
            s, e = (m.start(1), m.end(1)) if m.lastindex else (m.start(), m.end())
            hit_words = set(page_char_to_word_compact[s:e])
            hit_words -= covered
            if not hit_words:
                continue
            xs = [data['left'][i] for i in hit_words]
            ys = [data['top'][i] for i in hit_words]
            x2s = [data['left'][i] + data['width'][i] for i in hit_words]
            y2s = [data['top'][i] + data['height'][i] for i in hit_words]
            x0, y0 = min(xs), min(ys)
            w0 = max(x2s) - x0
            h0 = max(y2s) - y0
            _draw_redact(draw, x0, y0, w0, h0, style, font)
            total_hits += 1
            covered.update(hit_words)

    img.save(output)
    print(f"OK: {output} (命中 {total_hits} 处)")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python3 redact_image.py <source_path> <output_path> [custom_rules_json [style]]")
        sys.exit(1)
    redact_image(
        sys.argv[1], sys.argv[2],
        sys.argv[3] if len(sys.argv) > 3 else None,
        sys.argv[4] if len(sys.argv) > 4 else "mask",
    )
