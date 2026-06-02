# tasks

## 1. OpenSpec proposal

- [ ] 1.1 创建 proposal、design、tasks 和 knowledge-base spec delta
- [ ] 1.2 运行 `openspec validate 2026-06-02-knowledge-base-file-parsers-advanced --strict`

## 2. Parser dependencies and public API

- [ ] 2.1 Write failing tests：public API 可导入 `parse_pdf`、`parse_docx`、`parse_pptx`、`parse_xlsx` 和 `parse_document`
- [ ] 2.2 Verify red：运行 `uv run pytest tests/unit -x -q`，确认导入测试失败
- [ ] 2.3 Implement：新增依赖 `pypdf`、`python-docx`、`python-pptx`、`openpyxl`，并暴露 public API
- [ ] 2.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 3. Parser registry

- [ ] 3.1 Write failing tests：`parse_document` 根据 extension / MIME type 分发 text、Markdown、HTML、PDF、DOCX、PPTX、XLSX
- [ ] 3.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.3 Implement：实现 parser registry，connector 后续只调用 registry
- [ ] 3.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.5 Write failing tests：unsupported media type fail fast，错误不包含正文
- [ ] 3.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 3.7 Implement：补 unsupported / empty handling
- [ ] 3.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 4. PDF parser

- [ ] 4.1 Write failing tests：文本型 PDF 每个有文本 page 生成 section，metadata 包含 `page_number`
- [ ] 4.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 4.3 Implement：用 `pypdf` 实现 `parse_pdf`
- [ ] 4.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 4.5 Write failing tests：加密 PDF / 无可抽取文本 fail fast，错误摘要脱敏
- [ ] 4.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 4.7 Implement：补 PDF failure handling
- [ ] 4.8 Verify green：运行 `uv run pytest tests/unit -x -q`

## 5. DOCX parser

- [ ] 5.1 Write failing tests：DOCX paragraph 和 table cell 文本进入 sections，heading path 保留
- [ ] 5.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 5.3 Implement：用 `python-docx` 实现 `parse_docx`
- [ ] 5.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 6. PPTX parser

- [ ] 6.1 Write failing tests：PPTX 每个 slide 生成 section，metadata 包含 `slide_number`
- [ ] 6.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 6.3 Implement：用 `python-pptx` 实现 `parse_pptx`
- [ ] 6.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 7. XLSX parser

- [ ] 7.1 Write failing tests：XLSX 每个 non-empty sheet 生成 section，cell 文本以可检索形式保留，metadata 包含 `sheet_name`
- [ ] 7.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 7.3 Implement：用 `openpyxl` 实现 `parse_xlsx`
- [ ] 7.4 Verify green：运行 `uv run pytest tests/unit -x -q`

## 8. Local directory integration

- [ ] 8.1 Write failing tests：local directory source 识别 `.pdf`、`.docx`、`.pptx`、`.xlsx`
- [ ] 8.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 8.3 Implement：更新 local connector format mapping
- [ ] 8.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 8.5 Write failing tests：local sync 执行时通过 parser registry 解析高级文件，并保留 section metadata 到 chunks
- [ ] 8.6 Verify red：运行 `uv run pytest tests/integration -x -q`
- [ ] 8.7 Implement：更新 sync executor parse path
- [ ] 8.8 Verify green：运行 `uv run pytest tests/integration -x -q`

## 9. Google Drive integration

- [ ] 9.1 Write failing tests：Google Sheets 导出 `.xlsx` 后调用 xlsx parser；Google Slides 导出 `.pptx` 后调用 pptx parser
- [ ] 9.2 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 9.3 Implement：更新 Google Drive MIME mapping 和 export dispatch
- [ ] 9.4 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 9.5 Write failing tests：uploaded PDF / DOCX / PPTX / XLSX download 后走 parser registry
- [ ] 9.6 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 9.7 Implement：更新 Google Drive download parse path
- [ ] 9.8 Verify green：运行 `uv run pytest tests/unit -x -q`
- [ ] 9.9 Write failing tests：export/download 单文件失败记录 failed count，sync 继续后续 item，不记录正文
- [ ] 9.10 Verify red：运行 `uv run pytest tests/unit -x -q`
- [ ] 9.11 Implement：补 failure isolation
- [ ] 9.12 Verify green：运行 `uv run pytest tests/unit -x -q`

## 10. Documentation

- [ ] 10.1 Write failing tests：knowledge-base capability docs 标明 PDF / DOCX / PPTX / XLSX 已支持，OCR/VLM/扫描 PDF 不支持
- [ ] 10.2 Verify red：运行相关文档测试并确认失败，或新增文档测试
- [ ] 10.3 Implement：更新 `docs/capabilities/knowledge-base.md` 和 owner roadmap
- [ ] 10.4 Verify green：运行相关文档测试

## 11. 验证与归档

- [ ] 11.1 运行 `uv run ruff format src tests`
- [ ] 11.2 运行 `uv run ruff check src tests`
- [ ] 11.3 运行 `uv run mypy src`
- [ ] 11.4 运行 `uv run pytest -x -q`
- [ ] 11.5 运行 `openspec validate 2026-06-02-knowledge-base-file-parsers-advanced --strict`
- [ ] 11.6 运行 `git diff --check`
- [ ] 11.7 所有 checkbox 完成后归档 change 并验证 `openspec/specs/knowledge-base/spec.md`
