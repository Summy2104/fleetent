# tasks

## 1. OpenSpec proposal

- [x] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [x] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-file-parsers-advanced --strict`

## 2. Parser dependencies and public API

- [x] 2.1 Write failing tests：public API 可导入 `parse_pdf`、`parse_docx`、`parse_pptx`、`parse_xlsx` 和 `parse_document`
- [x] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`，确认导入测试失败
- [x] 2.3 Implement：新增依赖 `pypdf`、`python-docx`、`python-pptx`、`openpyxl`，并暴露 public API
- [x] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Parser registry

- [x] 3.1 Write failing tests：`parse_document` 根据 extension / MIME type 分发 text、Markdown、HTML、PDF、DOCX、PPTX、XLSX
- [x] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.3 Implement：实现 parser registry，connector 后续只调用 registry
- [x] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 3.5 Write failing tests：unsupported media type fail fast，错误不包含正文
- [x] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 3.7 Implement：补 unsupported / empty handling
- [x] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. PDF parser

- [x] 4.1 Write failing tests：文本型 PDF 每个有文本 page 生成 section，metadata 包含 `page_number`
- [x] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.3 Implement：用 `pypdf` 实现 `parse_pdf`
- [x] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 4.5 Write failing tests：加密 PDF / 无可抽取文本 fail fast，错误摘要脱敏
- [x] 4.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 4.7 Implement：补 PDF failure handling
- [x] 4.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 5. DOCX parser

- [x] 5.1 Write failing tests：DOCX paragraph 和 table cell 文本进入 sections，heading path 保留
- [x] 5.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 5.3 Implement：用 `python-docx` 实现 `parse_docx`
- [x] 5.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 6. PPTX parser

- [x] 6.1 Write failing tests：PPTX 每个 slide 生成 section，metadata 包含 `slide_number`
- [x] 6.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 6.3 Implement：用 `python-pptx` 实现 `parse_pptx`
- [x] 6.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 7. XLSX parser

- [x] 7.1 Write failing tests：XLSX 每个 non-empty sheet 生成 section，cell 文本以可检索形式保留，metadata 包含 `sheet_name`
- [x] 7.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 7.3 Implement：用 `openpyxl` 实现 `parse_xlsx`
- [x] 7.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 8. Local directory integration

- [x] 8.1 Write failing tests：local directory source 识别 `.pdf`、`.docx`、`.pptx`、`.xlsx`
- [x] 8.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 8.3 Implement：更新 local connector format mapping
- [x] 8.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 8.5 Write failing tests：local sync 执行时通过 parser registry 解析高级文件，并保留 section metadata 到 chunks
- [x] 8.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [x] 8.7 Implement：更新 sync executor parse path
- [x] 8.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 9. Google Drive integration

- [x] 9.1 Write failing tests：Google Sheets 导出 `.xlsx` 后调用 xlsx parser；Google Slides 导出 `.pptx` 后调用 pptx parser
- [x] 9.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 9.3 Implement：更新 Google Drive MIME mapping 和 export dispatch
- [x] 9.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 9.5 Write failing tests：uploaded PDF / DOCX / PPTX / XLSX download 后走 parser registry
- [x] 9.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 9.7 Implement：更新 Google Drive download parse path
- [x] 9.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [x] 9.9 Write failing tests：export/download 单文件失败记录 failed count，sync 继续后续 item，不记录正文
- [x] 9.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [x] 9.11 Implement：补 failure isolation
- [x] 9.12 Verify green：运行 `uv run pytest tests/unit -x -q`

## 10. Documentation

- [x] 10.1 Write failing tests：knowledge-base capability docs 标明 PDF / DOCX / PPTX / XLSX 已支持，OCR/VLM/扫描 PDF 不支持
- [x] 10.2 Verify red：运行相关文档测试并确认失败，或新增文档测试
- [x] 10.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 owner roadmap
- [x] 10.4 Verify green：运行相关文档测试

## 11. 验证与归档

- [x] 11.1 运行 `uv run ruff format src tests`
- [x] 11.2 运行 `uv run ruff check src tests`
- [x] 11.3 运行 `uv run mypy src`
- [x] 11.4 运行 `uv run pytest -x -q`
- [x] 11.5 运行 `openspec validate 2026-06-02-knowledge-base-file-parsers-advanced --strict`
- [x] 11.6 运行 `git diff --check`
- [x] 11.7 所有 checkbox 完成后归档 change 并验证 `openspec/specs/knowledge-base/spec.md`
