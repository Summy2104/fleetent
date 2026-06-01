## 0. 前置确认

- [x] 0.1 确认 Confluence MVP 只支持 Cloud API token，不做 Server / Data Center
- [x] 0.2 确认 credential 使用 `credential_ref`，不把真实 token 写入 connector config
- [x] 0.3 确认 MVP 不做 per-user Confluence ACL 映射
- [x] 0.4 确认源端 missing 默认 archive / mark missing，不物理删除 KB document
- [x] 0.5 确认默认测试不连接真实 Confluence

## 1. Confluence connector config and credential reference

- [x] 1.1 Write failing tests: Confluence connector config dataclass 可从 knowledge-base public API 导入
- [x] 1.2 Write failing tests: config 必须包含 connector_id、tenant_id、kb_id、base_url、username 和 API token credential_ref
- [x] 1.3 Write failing tests: config 支持 space scope、page scope 和 page include_children scope
- [x] 1.4 Write failing tests: API token 无效或权限不足时 connector 标记为 `auth_failed`
- [x] 1.5 Implement: config dataclass、credential_ref resolver 和 public exports
- [x] 1.6 Verify green: 运行 `uv run pytest tests/unit/test_confluence_connector.py -x -q`

## 2. Fake Confluence client and scope listing

- [x] 2.1 Write failing tests: space scope 列举 space pages
- [x] 2.2 Write failing tests: page scope 只列举指定 page
- [x] 2.3 Write failing tests: page include_children scope 列举指定 page 和 descendants
- [x] 2.4 Write failing tests: pagination 被完整处理
- [x] 2.5 Implement: Confluence client interface、fake client 和 scope listing adapter
- [x] 2.6 Verify green: 运行 `uv run pytest tests/unit/test_confluence_connector.py -x -q`

## 3. Page fetch and parsing

- [x] 3.1 Write failing tests: Confluence page fetch 展开 storage HTML、version、space 和 ancestors
- [x] 3.2 Write failing tests: storage HTML 调用现有 HTML parser
- [x] 3.3 Write failing tests: title、space key、ancestors / path text 写入 parsed metadata
- [x] 3.4 Implement: page fetch / parser dispatch / metadata mapping
- [x] 3.5 Verify green: 运行 `uv run pytest tests/unit/test_confluence_connector.py -x -q`

## 4. Sync planning

- [x] 4.1 Write failing tests: 新 Confluence page 生成 `ingest_new`
- [x] 4.2 Write failing tests: version / modified time 变化生成 `reingest_changed`
- [x] 4.3 Write failing tests: 未变化 page 生成 `skip_unchanged`
- [x] 4.4 Write failing tests: 历史 source state 在当前 scope listing 中缺失时生成 `archive_missing`
- [x] 4.5 Implement: Confluence sync planner using source state
- [x] 4.6 Verify green: 运行 `uv run pytest tests/unit/test_confluence_sync_planner.py -x -q`

## 5. Sync execution

- [x] 5.1 Write failing tests: `ingest_new` 调用 HTML parser 和 `ingest_parsed()`，写入指定 tenant/kb
- [x] 5.2 Write failing tests: `reingest_changed` 更新 KB document / chunks 和 source state
- [x] 5.3 Write failing tests: `archive_missing` 不调用 physical `delete()`，且 archived 内容默认不参与 search
- [x] 5.4 Write failing tests: 单 item 失败不阻塞后续 item
- [x] 5.5 Implement: execute Confluence sync plan
- [x] 5.6 Verify green: 运行 `uv run pytest tests/integration/test_confluence_sync.py -x -q`

## 6. Rate limit and retry

- [x] 6.1 Write failing tests: 429 + Retry-After 会等待后重试
- [x] 6.2 Write failing tests: 超过重试上限后记录 item failure，不阻塞后续 item
- [x] 6.3 Implement: requests_per_minute、Retry-After 和 bounded retry
- [x] 6.4 Verify green: 运行 `uv run pytest tests/unit/test_confluence_connector.py -x -q`

## 7. Manual sync public API

- [x] 7.1 Write failing tests: `plan_confluence_sync()` 和 `sync_confluence()` 可从 knowledge-base public API 导入
- [x] 7.2 Write failing tests: `sync_confluence()` 通过 planner + executor 执行，不边扫描边写 KB
- [x] 7.3 Write failing tests: summary 包含 scanned、planned、ingested、changed、unchanged、archived、failed 和 auth_failed
- [x] 7.4 Implement: public manual sync API and summary dataclasses
- [x] 7.5 Verify green: 运行 `uv run pytest tests/integration/test_confluence_sync.py -x -q`

## 8. Optional real Confluence smoke

- [x] 8.1 Write failing tests: 未设置 `FLEETENT_CONFLUENCE_SMOKE=1` 时真实 smoke skip
- [x] 8.2 Write failing tests: 缺少 base URL、username、credential_ref 或 scope 时真实 smoke skip
- [x] 8.3 Implement: opt-in smoke test scaffolding
- [x] 8.4 Verify green: 运行 `uv run pytest tests/e2e/test_confluence_connector_smoke.py -q`

## 9. Docs and final verification

- [x] 9.1 更新 `docs/capabilities/knowledge-base.md`
- [x] 9.2 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 9.3 文档写明 Confluence credential 绑定 connector，不绑定最终提问用户
- [x] 9.4 文档写明 MVP 不做 per-user Confluence ACL，访问控制由 KB scope / agent binding 承担
- [x] 9.5 文档写明 missing 默认 archive，不物理删除
- [x] 9.6 文档写明只支持 Confluence Cloud API token，Server / Data Center 后置
- [x] 9.7 运行 `uv run ruff format src tests`
- [x] 9.8 运行 `uv run ruff check src tests`
- [x] 9.9 运行 `uv run mypy src`
- [x] 9.10 运行 `uv run pytest -x -q`
- [x] 9.11 运行 `openspec validate knowledge-base-connectors-confluence --strict`
- [x] 9.12 运行 `git diff --check`
