# Design

## 目标

为 knowledge-base 增加第一批高级文件 parser，使 local source 和 Google Drive connector 能处理常见企业文档：

- 文本型 PDF
- `.docx`
- `.pptx`
- `.xlsx`

输出继续归一到 `ParsedDocument` / `ParsedSection`，后续 ingest、chunking、vector index、keyword index 和
source attribution 不需要理解具体文件格式。

## Parser Registry

新增 parser registry，负责根据文件名和 MIME type 选择 parser。

建议 public API：

```python
def parse_document(filename: str, content: bytes | str, mime_type: str | None = None) -> ParsedDocument:
    ...
```

行为：

- `.txt` / `text/plain`：调用 `parse_text`。
- `.md` / Markdown MIME：调用 `parse_markdown`。
- `.html` / `.htm` / `text/html`：调用 `parse_html`。
- `.pdf` / `application/pdf`：调用 `parse_pdf`。
- `.docx`：调用 `parse_docx`。
- `.pptx`：调用 `parse_pptx`。
- `.xlsx`：调用 `parse_xlsx`。
- unsupported type fail fast，交由 connector / sync executor 记录 skipped 或 failed item。

registry 是 connector 和 local source 的唯一 parser 入口，避免每个 connector 自己复制格式分发逻辑。

## Parsed Metadata

`ParsedDocument` 不新增字段。格式定位信息放到 `metadata`。

文档 metadata：

```text
filename
format
parser
source_mime_type
warnings
```

section metadata：

```text
path
page_number      # PDF
slide_number     # PPTX
sheet_name       # XLSX
row_range        # XLSX 可选
```

约束：

- metadata 不存文件正文。
- metadata 不存 credential。
- `warnings` 只保存脱敏提示，例如 `encrypted_file_unsupported`、`empty_page_skipped`。

## PDF Parser

使用 `pypdf` 解析文本型 PDF。

行为：

- 每个有文本的 page 生成一个 section。
- section title 为 `Page N`。
- section metadata 包含 `page_number` 和 `path`。
- 空 page 跳过，并在 document metadata warnings 中记录。
- 加密 PDF fail fast，错误摘要为加密 / unsupported，不输出正文。
- 扫描版 PDF 如果没有可抽取文本，fail fast 或返回无 sections 后由统一空文档处理。

不做：

- OCR。
- 图片提取。
- 表格结构化。

## DOCX Parser

使用 `python-docx`。

行为：

- 抽取 paragraph 文本。
- 抽取 table cell 文本，转为可检索纯文本。
- 使用 heading paragraph 拆分 sections；没有 heading 时生成 body section。
- section metadata 包含 heading path。

不做：

- 批注。
- 修订记录。
- 页码定位。

## PPTX Parser

使用 `python-pptx`。

行为：

- 每个 slide 生成一个 section。
- 抽取 slide shapes 中可访问的文本。
- section title 为 slide title；没有 title 时为 `Slide N`。
- section metadata 包含 `slide_number` 和 `path`。

不做：

- speaker notes。
- 图片 / 图表语义理解。
- 动画或隐藏对象。

## XLSX Parser

使用 `openpyxl`。

行为：

- 每个 non-empty sheet 生成一个或多个 section。
- 第一版可以每个 sheet 一个 section，将非空行转为可检索文本。
- 行内 cell 用 ` | ` 拼接，行间用换行。
- section metadata 包含 `sheet_name`，可选 `row_range`。

不做：

- formula evaluation。
- 单元格类型保真。
- 表格 schema / table QA。
- 图表和图片。

## Google Drive 对齐

Google Drive connector 继续复用 parser registry。

映射：

- Google Docs：导出 HTML，调用 registry / HTML parser。
- Google Sheets：导出 `.xlsx`，调用 registry / xlsx parser。
- Google Slides：导出 `.pptx`，调用 registry / pptx parser。
- 普通 uploaded PDF / Office 文件：download 原始 bytes 后交给 registry。

如果 export 或 download 失败：

- 单文件失败。
- sync 继续后续 item。
- summary 记录 failed count 和脱敏错误摘要。

## 失败处理

解析失败分为：

- unsupported media type：skipped。
- encrypted file：failed item，错误摘要脱敏。
- scanned PDF / empty extraction：failed item 或 skipped，implementation 需保持一致并在 tests 中固定。
- parser exception：failed item，脱敏错误摘要。

执行要求：

- 单文件失败不让整次 sync 失败。
- 不记录文件正文。
- 不记录 credential。
- source id / filename / parser / sanitized error summary 可以进入 status 或 summary。

## 测试策略

Unit tests：

- 每种 parser 一个最小 fixture。
- parser registry 按 extension / MIME type 分发。
- unsupported / encrypted / empty extraction 的失败行为。

Integration tests：

- local directory sync 支持 `.pdf`、`.docx`、`.pptx`、`.xlsx`。
- parsed ingest 后 chunk metadata 保留 page / slide / sheet 等 section metadata。

Connector fake tests：

- Google Sheets export `.xlsx` 后走 xlsx parser。
- Google Slides export `.pptx` 后走 pptx parser。
- Google Drive uploaded PDF / Office 文件 download 后走 registry。
- export/download 单文件失败不终止整次 sync。

Evaluation：

- 不强制真实大文件或真实 SaaS。
- 使用可控小 fixture 验证可检索文本。

## 依赖和安全

新增依赖仅用于本地文件解析：

- `pypdf`
- `python-docx`
- `python-pptx`
- `openpyxl`

不引入：

- LlamaIndex
- LangChain
- docling
- unstructured
- OCR engine
- VLM
- 外部解析服务

## 与后续 specs 的关系

本 change 是 `knowledge-base-entity-relation-extraction` 的前置之一：只有更多企业文件能进入 KB，实体关系抽取才有足够数据基础。

本 change 不做 query planner，也不改变 retrieval mode。解析后的内容继续进入既有 chunking、keyword、vector 和 hybrid search。
