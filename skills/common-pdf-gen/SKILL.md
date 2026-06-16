---
name: common-pdf-gen
description: 使用 reportlab 生成 PDF 文件。当 agent 需要生成 PDF 报告、文档时使用。触发词：生成PDF、PDF报告、导出PDF、输出PDF
status: active
metadata:
  author: RD Team
  version: 1.0.0
triggers:
  - 生成PDF
  - PDF报告
  - 导出PDF
  - 输出PDF
  - generate PDF
---

# PDF 文件生成

用 `run_code`（沙箱内 Python）调用 `reportlab` 库生成 PDF。

## 基本模板

```python
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
import os

# 注册中文字体：用 reportlab 内置 CID 字体 STSong-Light —— 无需任何字体文件，
# Linux/容器/macOS 一致可用。切勿用 TTFont 加载系统 NotoSansCJK.ttc
# （TTC/PostScript-outline 字体，reportlab 加载会失败并触发长时间重试）。
CJK_FONT = 'STSong-Light'
pdfmetrics.registerFont(UnicodeCIDFont(CJK_FONT))

# 输出路径（写到沙箱 workspace 下，便于后续 send_file 投递）
outbound_dir = os.environ.get('OUTBOUND_DIR', '/workspace/outbound')
output_path = os.path.join(outbound_dir, '报告', '文件名.pdf')
os.makedirs(os.path.dirname(output_path), exist_ok=True)

doc = SimpleDocTemplate(output_path, pagesize=A4)
styles = getSampleStyleSheet()
style_normal = ParagraphStyle('normal_cjk', parent=styles['Normal'], fontName=CJK_FONT)
style_title = ParagraphStyle('title_cjk', parent=styles['Title'], fontName=CJK_FONT)

story = [Paragraph('标题', style_title), Spacer(1, 12)]
story.append(Paragraph('正文内容', style_normal))
doc.build(story)
```

## 输出与发送

1. 文件写入 `$OUTBOUND_DIR/{关键词}/{YYYY-MM}/文件名.pdf`（沙箱 workspace 下）
2. 用 `send_file` 把生成的 PDF 发回当前对话，例如 `send_file(path="outbound/报告/文件名.pdf")`（workspace 相对路径或 `/exchange` 路径均可）
3. 聊天中只输出 3-5 行摘要，不输出完整内容

## 注意事项

- 只用 `reportlab`，不用其他 PDF 库
- 所有中文内容必须使用 `STSong-Light`（reportlab 内置 CID 字体）；**不要**用 `TTFont` 加载系统 `.ttc`（如 NotoSansCJK），否则加载失败或显示方块
- `Paragraph` 中的特殊字符（`<`, `>`, `&`）需要 HTML 转义
- 长文本自动换行，无需手动处理
