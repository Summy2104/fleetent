## ADDED Requirements

### Requirement: Advanced parser public API
knowledge-base SHALL provide local parsers for text-based PDF, DOCX, PPTX and XLSX documents without using AI frameworks or external parsing services.

#### Scenario: Advanced parser API is importable
- **WHEN** 调用方导入 `parse_pdf`、`parse_docx`、`parse_pptx`、`parse_xlsx` 和 `parse_document`
- **THEN** 导入成功

#### Scenario: Advanced parser dependencies are local only
- **WHEN** 查看 runtime dependencies
- **THEN** 可以使用 `pypdf`、`python-docx`、`python-pptx` 和 `openpyxl`
- **AND** 不包含 LlamaIndex、LangChain、docling、unstructured、OCR engine 或 VLM dependency

### Requirement: Parser registry dispatch
knowledge-base SHALL provide a parser registry that maps supported file extensions and MIME types to the correct parser.

#### Scenario: Registry dispatches basic formats
- **WHEN** 调用 `parse_document` 解析 `.txt`、`.md`、`.html` 或 `.htm`
- **THEN** registry 分别调用 text、Markdown 或 HTML parser

#### Scenario: Registry dispatches advanced formats
- **WHEN** 调用 `parse_document` 解析 `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** registry 分别调用 PDF、DOCX、PPTX 或 XLSX parser

#### Scenario: Registry dispatches by MIME type
- **WHEN** filename 缺少可识别 extension
- **AND** MIME type 是 supported type
- **THEN** registry 使用 MIME type 选择 parser

#### Scenario: Unsupported media type fails fast
- **WHEN** registry 收到 unsupported extension 和 MIME type
- **THEN** registry fail fast
- **AND** 错误信息不包含文件正文

### Requirement: Text-based PDF parser
knowledge-base SHALL parse text-based PDF files into sections with page metadata.

#### Scenario: PDF pages become sections
- **WHEN** parser 解析包含可抽取文本的 PDF
- **THEN** 每个有文本的 page 生成一个 section
- **AND** section metadata 包含 `page_number`

#### Scenario: Empty PDF extraction fails safely
- **WHEN** parser 解析扫描版或没有可抽取文本的 PDF
- **THEN** parser fail fast 或返回统一 empty-content failure
- **AND** 错误信息不包含文件正文

#### Scenario: Encrypted PDF fails safely
- **WHEN** parser 解析加密 PDF
- **THEN** parser fail fast
- **AND** 错误摘要说明 encrypted / unsupported
- **AND** 不输出文件正文

### Requirement: DOCX parser
knowledge-base SHALL parse DOCX paragraph and table text into searchable parsed sections.

#### Scenario: DOCX paragraphs are searchable
- **WHEN** parser 解析包含 paragraph 的 DOCX
- **THEN** paragraph 文本进入 parsed sections

#### Scenario: DOCX tables are searchable text
- **WHEN** parser 解析包含 table 的 DOCX
- **THEN** table cell 文本进入 parsed sections
- **AND** 不要求保留结构化 table schema

#### Scenario: DOCX headings preserve path
- **WHEN** DOCX 包含 heading paragraphs
- **THEN** sections metadata 保留 heading path

### Requirement: PPTX parser
knowledge-base SHALL parse PowerPoint slide text into sections with slide metadata.

#### Scenario: PPTX slides become sections
- **WHEN** parser 解析 PPTX
- **THEN** 每个包含文本的 slide 生成 section
- **AND** section metadata 包含 `slide_number`

#### Scenario: PPTX title is used when available
- **WHEN** slide 包含标题文本
- **THEN** section title 使用 slide title
- **AND** 没有标题时使用 `Slide N`

### Requirement: XLSX parser
knowledge-base SHALL parse Excel workbook cell text into searchable sections with sheet metadata.

#### Scenario: XLSX sheets become sections
- **WHEN** parser 解析 XLSX
- **THEN** 每个 non-empty sheet 生成 section
- **AND** section metadata 包含 `sheet_name`

#### Scenario: XLSX cells become searchable text
- **WHEN** sheet 包含非空 cells
- **THEN** cell values 以可检索文本形式进入 section
- **AND** 不要求保留结构化 table schema 或公式计算结果

### Requirement: Advanced local source parsing
local directory source SHALL include PDF, DOCX, PPTX and XLSX files in sync planning and parse them through the parser registry.

#### Scenario: Local source supports advanced extensions
- **WHEN** local directory 包含 `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** planner 将这些文件识别为 supported files

#### Scenario: Local sync parses advanced files
- **WHEN** executor 处理 advanced file ingest item
- **THEN** 它通过 parser registry 解析文件
- **AND** 调用 `ingest_parsed()` 写入 KB

#### Scenario: Advanced section metadata reaches chunks
- **WHEN** advanced parsed section 生成 chunk
- **THEN** chunk metadata 保留 page、slide 或 sheet 等 section metadata

### Requirement: Google Drive advanced content parsing
Google Drive connector SHALL map Google Sheets, Google Slides and uploaded Office/PDF files into the parser registry.

#### Scenario: Google Sheets export uses XLSX parser
- **WHEN** connector 同步 Google Sheets
- **THEN** 它通过 Drive export API 导出 `.xlsx`
- **AND** 调用 xlsx parser 生成 parsed document

#### Scenario: Google Slides export uses PPTX parser
- **WHEN** connector 同步 Google Slides
- **THEN** 它通过 Drive export API 导出 `.pptx`
- **AND** 调用 pptx parser 生成 parsed document

#### Scenario: Uploaded PDF and Office files use registry
- **WHEN** connector 同步 uploaded `.pdf`、`.docx`、`.pptx` 或 `.xlsx`
- **THEN** 它 download 原始 bytes
- **AND** 通过 parser registry 解析

#### Scenario: Per-file export failure is isolated
- **WHEN** Google Drive export 或 download 某个文件失败
- **THEN** executor 记录 failed count 和脱敏错误摘要
- **AND** 继续处理后续 item
- **AND** 不记录文件正文或 credential

### Requirement: Advanced parser exclusions
knowledge-base advanced parsers SHALL keep OCR, VLM, scanned PDF, encrypted file parsing and structured table QA out of scope.

#### Scenario: OCR and VLM remain unsupported
- **WHEN** parser 遇到只能通过 OCR 或 VLM 理解的内容
- **THEN** parser 不调用 OCR、VLM 或外部解析服务
- **AND** 返回 unsupported / empty extraction failure

#### Scenario: Structured table QA remains out of scope
- **WHEN** parser 解析 DOCX 或 XLSX table
- **THEN** parser 只输出可检索文本
- **AND** 不输出 table QA 专用结构化模型

## MODIFIED Requirements

### Requirement: Parser dependency boundary
基础 parser SHALL 不引入 LlamaIndex、LangChain、docling、VLM 或外部解析服务依赖。高级 parser 可以引入
本地 PDF / Office 解析依赖，但不得引入 AI framework、OCR engine、VLM 或外部解析服务。

#### Scenario: No AI framework parser dependency
- **WHEN** parser changes 完成
- **THEN** runtime dependency 不包含 LlamaIndex、LangChain、docling 或 unstructured
- **AND** 不包含 OCR engine 或 VLM dependency

### Requirement: Google Drive content parsing
Google Drive connector SHALL map supported Drive content into knowledge-base parser registry.

#### Scenario: Google Docs export uses HTML parser
- **WHEN** connector 同步 Google Docs
- **THEN** 它通过 Drive export API 导出 HTML
- **AND** 调用 HTML parser 生成 parsed document

#### Scenario: Plain text uses text parser
- **WHEN** connector 同步 plain text 文件
- **THEN** 它调用 text parser

#### Scenario: Markdown uses markdown parser
- **WHEN** connector 同步 Markdown 文件
- **THEN** 它调用 Markdown parser

#### Scenario: HTML file uses HTML parser
- **WHEN** connector 同步 HTML 文件
- **THEN** 它调用 HTML parser

#### Scenario: Google Sheets and Slides are exported to supported Office formats
- **WHEN** connector 遇到 Google Sheets 或 Google Slides
- **THEN** Google Sheets 导出为 `.xlsx`
- **AND** Google Slides 导出为 `.pptx`
- **AND** 导出内容通过 parser registry 解析
