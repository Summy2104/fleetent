## ADDED Requirements

### Requirement: Basic parser public API
系统 SHALL 提供无 AI 框架依赖的基础 parser API，将 text、Markdown 和 lightweight HTML 转换为
structured parsed sections。

#### Scenario: Parser API is importable
- **WHEN** 调用方导入 `ParsedSection`、`ParsedDocument`、`parse_text`、`parse_markdown` 和 `parse_html`
- **THEN** 导入成功

#### Scenario: Parsed document shape
- **WHEN** parser 返回 `ParsedDocument`
- **THEN** 结果包含 filename、format、sections 和 metadata
- **AND** 每个 section 包含 title、text、level 和 metadata

### Requirement: Text parser
系统 SHALL 支持 plain text parser，用于无结构文本导入。

#### Scenario: Text body section
- **WHEN** 解析非空 text
- **THEN** parser 返回一个 body section

#### Scenario: Empty text rejected
- **WHEN** text 内容为空或全空白
- **THEN** parser fail fast

### Requirement: Markdown parser
系统 SHALL 支持基础 Markdown section parser。

#### Scenario: Markdown headings create sections
- **WHEN** Markdown 包含多级 heading
- **THEN** parser 按 heading 生成 sections
- **AND** section metadata 保留 heading path

#### Scenario: Fenced code blocks are preserved
- **WHEN** Markdown fenced code block 内包含 `#`
- **THEN** parser 不把 code block 内容误识别为 heading

#### Scenario: Empty sections are removed
- **WHEN** heading 下没有有效文本
- **THEN** parser 不输出空 section

### Requirement: Lightweight HTML parser
系统 SHALL 支持 lightweight HTML parser，用于后续 Confluence / HTML 文档适配。

#### Scenario: Unsafe or non-content elements are ignored
- **WHEN** HTML 包含 script 或 style
- **THEN** parser 输出不包含这些内容

#### Scenario: HTML headings and body text create sections
- **WHEN** HTML 包含 title、heading 和段落
- **THEN** parser 输出对应 sections

#### Scenario: Simple tables become searchable text
- **WHEN** HTML 包含简单 table
- **THEN** parser 将 table cells 转为可检索文本

### Requirement: Parsed ingest adapter
系统 SHALL 允许 core ingest 消费 parsed sections 并保留 section metadata。

#### Scenario: Parsed sections are ingested
- **WHEN** 调用 parsed ingest API
- **THEN** 系统为 parsed sections 生成 chunks 并写入 vector_store

#### Scenario: Chunk metadata includes section context
- **WHEN** parsed section 生成 chunk
- **THEN** chunk metadata 保留 section title 或 heading path

### Requirement: Parser dependency boundary
基础 parser SHALL 不引入 LlamaIndex、LangChain、docling、PDF/Office parser 或 VLM 依赖。

#### Scenario: No AI framework parser dependency
- **WHEN** basic parser change 完成
- **THEN** runtime dependency 不包含 LlamaIndex、LangChain 或 docling
