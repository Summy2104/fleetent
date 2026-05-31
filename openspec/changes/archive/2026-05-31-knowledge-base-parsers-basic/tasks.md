## 0. 前置确认

- [x] 0.1 确认 `knowledge-base-core` 已在 suite 分支完成并验证
- [x] 0.2 确认本 change 不引入 PDF/Office/docling/image/VLM 依赖
- [x] 0.3 确认 parser 输出不暴露 LlamaIndex 类型

## 1. Parser dataclasses and API

- [x] 1.1 Write failing tests: `ParsedSection`、`ParsedDocument` 和 parse functions 可导入
- [x] 1.2 Write failing tests: parser output 包含 filename、format、sections 和 metadata
- [x] 1.3 实现 parser public API skeleton
- [x] 1.4 运行 `uv run pytest tests/unit -x -q`

## 2. Text parser

- [x] 2.1 Write failing tests: text parser 过滤空白内容并生成 body section
- [x] 2.2 Write failing tests: empty text fail fast
- [x] 2.3 实现 text parser
- [x] 2.4 运行 `uv run pytest tests/unit -x -q`

## 3. Markdown parser

- [x] 3.1 Write failing tests: heading 生成 section title/path/level
- [x] 3.2 Write failing tests: fenced code block 不被误识别为 heading
- [x] 3.3 Write failing tests: 空 section 被过滤
- [x] 3.4 实现 markdown parser
- [x] 3.5 运行 `uv run pytest tests/unit -x -q`

## 4. HTML parser

- [x] 4.1 Write failing tests: script/style 被移除
- [x] 4.2 Write failing tests: title/headings/body text 被提取为 sections
- [x] 4.3 Write failing tests: simple table 被转为可检索文本
- [x] 4.4 实现轻量 HTML parser；如需要新增依赖必须先确认收益
- [x] 4.5 运行 `uv run pytest tests/unit -x -q`

## 5. Parsed ingest integration

- [x] 5.1 Write failing tests: parsed sections 可导入 core ingest 并生成 chunks
- [x] 5.2 Write failing tests: chunk metadata 保留 section title/path
- [x] 5.3 实现 `ingest_parsed` 或等价 adapter
- [x] 5.4 更新 `docs/capabilities/knowledge-base.md`
- [x] 5.5 运行 `uv run pytest -x -q`
- [x] 5.6 运行 `uv run ruff format src tests`
- [x] 5.7 运行 `uv run ruff check src tests`
- [x] 5.8 运行 `uv run mypy src`
- [x] 5.9 运行 `openspec validate knowledge-base-parsers-basic`
