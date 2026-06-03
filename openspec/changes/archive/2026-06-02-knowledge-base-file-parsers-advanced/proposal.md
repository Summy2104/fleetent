# knowledge-base-file-parsers-advanced

## Why

当前 knowledge-base parser 已支持 plain text、Markdown 和 lightweight HTML。企业知识库真实内容中大量存在
PDF、Word、PowerPoint 和 Excel 文件；如果这些文件继续被跳过，Google Drive / Confluence / local source
即使 sync 能跑通，也无法覆盖常见企业文档。

本 change 补齐第一批高级文件解析能力，但保持 on-prem、SQLite-first 和无 AI 框架约束：只做本地文本抽取，
不引入 OCR、VLM 或外部解析服务。

## What Changes

- 新增文本型 PDF parser。
- 新增 `.docx` parser。
- 新增 `.pptx` parser。
- 新增 `.xlsx` parser。
- 新增 parser registry，根据 extension / MIME type 分发到 text / Markdown / HTML / PDF / Office parser。
- local directory connector 支持 `.pdf`、`.docx`、`.pptx`、`.xlsx`。
- Google Drive connector 将 Google Sheets 导出为 `.xlsx` 后复用 xlsx parser；将 Google Slides 导出为 `.pptx` 后复用 pptx parser。
- parser 输出继续使用 `ParsedDocument` / `ParsedSection`，并在 section metadata 中保留页码、slide、sheet 等定位信息。
- 单文件解析失败不让整次 sync 失败；失败摘要脱敏，不记录文件正文。

## 模块边界影响

- owning package：`intelligence.knowledge_base`。
- public API surface：
  - 新增 `parse_pdf`、`parse_docx`、`parse_pptx`、`parse_xlsx`。
  - 新增 parser registry API，例如 `parse_document(filename, content, mime_type=None)` 或等价函数。
- owned tables：无新增。
- config namespace：无新增。
- cross-module dependencies：
  - local / Google Drive connector 通过 knowledge-base parser registry 调用 parser。
  - vector store / observability / long-term context 不新增依赖。
- migration / shim plan：无 DB migration，无 legacy shim。

## Dependencies

允许新增以下本地解析依赖：

- `pypdf`
- `python-docx`
- `python-pptx`
- `openpyxl`

这些依赖只在本地解析文件，不调用外部服务，不引入 LlamaIndex / LangChain / docling / unstructured。

## 非目标

- 不做 OCR。
- 不做 VLM / 图片理解。
- 不支持扫描版 PDF。
- 不做 PDF 表格结构化抽取。
- 不解析 Office 批注、修订记录、speaker notes。
- 不解析加密文件。
- 不做附件递归解析。
- 不做 table QA 或结构化表格查询。
