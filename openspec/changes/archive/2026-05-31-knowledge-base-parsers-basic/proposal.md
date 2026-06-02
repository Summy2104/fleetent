## Why

`knowledge-base-core` only accepts already-normalized text / markdown content. To inherit the useful
parts of `knowledge-bridge` without bringing in LlamaIndex or heavy document dependencies, fleetent needs
a small parser layer that turns plain text, Markdown and lightweight HTML into structured sections.

This change expands the input surface while keeping connectors, Office/PDF parsing and image/VLM out of
scope.

## What Changes

- Add parser dataclasses:
  - `ParsedSection(title, text, level, metadata)`
  - `ParsedDocument(filename, format, sections, metadata)`
- Add parser public API:
  - `parse_text(filename, content)`
  - `parse_markdown(filename, content)`
  - `parse_html(filename, content)`
- Add `ingest_parsed(parsed, tenant_id, kb_id, source, source_url)` or equivalent core adapter.
- Text parser filters empty content and preserves a body section.
- Markdown parser recognizes heading hierarchy, protects fenced code blocks and removes empty sections.
- HTML parser strips scripts/styles, extracts title/headings/body text and normalizes simple tables to text.
- Parser output preserves section title/path metadata so chunks can keep source context.

## Out of Scope

- No PDF/DOCX/PPTX/XLSX parser.
- No docling, LlamaIndex, pandas, PyMuPDF or Office runtime dependency.
- No image/VLM parsing.
- No Confluence / Google Drive connector.
- No hybrid retrieval change.

## Dependencies

- Requires `knowledge-base-core` merged into the suite branch.

## Parallelism

After `knowledge-base-core`, this can run in parallel with `knowledge-base-hybrid-search` and
`knowledge-base-retrieval-evaluation` as long as workers do not edit the same files beyond
`docs/capabilities/knowledge-base.md` and `openspec` tasks.

## Impact

- **Code**: adds parser module under `intelligence.knowledge_base`.
- **Database**: no schema changes expected.
- **Tests**: unit tests for parser behavior; integration tests for parsed ingest.
