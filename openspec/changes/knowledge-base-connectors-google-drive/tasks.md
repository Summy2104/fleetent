## 0. 前置确认

- [ ] 0.1 确认第一批 remote connector 是 Google Drive，不是 Confluence
- [ ] 0.2 确认认证方式使用 OAuth 用户授权，不做 service account / domain-wide delegation
- [ ] 0.3 确认 MVP 不做 per-user Google Drive ACL 映射
- [ ] 0.4 确认源端 missing 默认 archive / mark missing，不物理删除 KB document
- [ ] 0.5 确认默认测试不连接真实 Google API

## 1. Google Drive connector config and credential reference

- [ ] 1.1 Write failing tests: Google Drive connector config dataclass 可从 knowledge-base public API 导入
- [ ] 1.2 Write failing tests: config 必须包含 connector_id、tenant_id、kb_id、folder_id 和 OAuth `credential_ref`
- [ ] 1.3 Write failing tests: OAuth token refresh 失败时 connector 标记为 `auth_failed`
- [ ] 1.4 Write failing tests: MVP 支持 file-based credential_ref，且不要求新增 credential 表
- [ ] 1.5 Implement: config dataclass、credential_ref resolver 和 public exports
- [ ] 1.6 Verify green: 运行 `uv run pytest tests/unit/test_google_drive_connector.py -x -q`

## 2. Fake Drive client and folder listing

- [ ] 2.1 Write failing tests: connector 只列举指定 `folder_id`
- [ ] 2.2 Write failing tests: unsupported MIME type 被跳过并计入 summary
- [ ] 2.3 Write failing tests: Google Docs metadata 被识别为 export HTML
- [ ] 2.4 Write failing tests: Google Sheets / Slides 在 MVP 中作为 unsupported 跳过
- [ ] 2.5 Implement: Drive client interface、fake client 和 folder listing adapter
- [ ] 2.6 Verify green: 运行 `uv run pytest tests/unit/test_google_drive_connector.py -x -q`

## 3. Parsing and content fetch

- [ ] 3.1 Write failing tests: Google Docs 通过 export HTML 后调用现有 HTML parser
- [ ] 3.2 Write failing tests: plain text 调用 text parser
- [ ] 3.3 Write failing tests: Markdown 调用 Markdown parser
- [ ] 3.4 Write failing tests: HTML 文件调用 HTML parser
- [ ] 3.5 Implement: content fetch / export and parser dispatch
- [ ] 3.6 Verify green: 运行 `uv run pytest tests/unit/test_google_drive_connector.py -x -q`

## 4. Sync planning

- [ ] 4.1 Write failing tests: 新 Google Drive 文件生成 `ingest_new`
- [ ] 4.2 Write failing tests: revision / modified time / content hash 变化生成 `reingest_changed`
- [ ] 4.3 Write failing tests: 未变化文件生成 `skip_unchanged`
- [ ] 4.4 Write failing tests: 历史 source state 在当前 listing 中缺失时生成 `archive_missing`
- [ ] 4.5 Implement: Google Drive sync planner using source state
- [ ] 4.6 Verify green: 运行 `uv run pytest tests/unit/test_google_drive_sync_planner.py -x -q`

## 5. Sync execution

- [ ] 5.1 Write failing tests: `ingest_new` 调用 parser 和 `ingest_parsed()`，写入指定 tenant/kb
- [ ] 5.2 Write failing tests: `reingest_changed` 更新 KB document / chunks 和 source state
- [ ] 5.3 Write failing tests: `archive_missing` 不调用 physical `delete()`，且 archived 内容默认不参与 search
- [ ] 5.4 Write failing tests: 单 item 失败不阻塞后续 item
- [ ] 5.5 Implement: execute Google Drive sync plan
- [ ] 5.6 Verify green: 运行 `uv run pytest tests/integration/test_google_drive_sync.py -x -q`

## 6. Manual sync public API

- [ ] 6.1 Write failing tests: `plan_google_drive_sync()` 和 `sync_google_drive()` 可从 knowledge-base public API 导入
- [ ] 6.2 Write failing tests: `sync_google_drive()` 通过 planner + executor 执行，不边扫描边写 KB
- [ ] 6.3 Write failing tests: summary 包含 scanned、planned、ingested、changed、unchanged、unsupported、archived、failed 和 auth_failed
- [ ] 6.4 Implement: public manual sync API and summary dataclasses
- [ ] 6.5 Verify green: 运行 `uv run pytest tests/integration/test_google_drive_sync.py -x -q`

## 7. Optional real Google Drive smoke

- [ ] 7.1 Write failing tests: 未设置 `FLEETENT_GOOGLE_DRIVE_SMOKE=1` 时真实 smoke skip
- [ ] 7.2 Write failing tests: 缺少 OAuth credential_ref 或 folder id 时真实 smoke skip
- [ ] 7.3 Implement: opt-in smoke test scaffolding
- [ ] 7.4 Verify green: 运行 `uv run pytest tests/e2e/test_google_drive_connector_smoke.py -q`

## 8. Docs and final verification

- [ ] 8.1 更新 `docs/capabilities/knowledge-base.md`
- [ ] 8.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 8.3 文档写明 OAuth token 绑定 connector，不绑定最终提问用户
- [ ] 8.4 文档写明 MVP 不做 per-user Drive ACL，访问控制由 KB scope / agent binding 承担
- [ ] 8.5 文档写明 missing 默认 archive，不物理删除
- [ ] 8.6 文档写明 credential_ref MVP 可指向本地 token 文件，后续可迁移到 credential store / secret manager
- [ ] 8.7 文档写明 Google Docs / Sheets 结构化解析后置
- [ ] 8.8 运行 `uv run ruff format src tests`
- [ ] 8.9 运行 `uv run ruff check src tests`
- [ ] 8.10 运行 `uv run mypy src`
- [ ] 8.11 运行 `uv run pytest -x -q`
- [ ] 8.12 运行 `openspec validate knowledge-base-connectors-google-drive --strict`
- [ ] 8.13 运行 `git diff --check`
