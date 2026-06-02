## 0. 前置确认

- [ ] 0.1 确认本 change 只做 Admin CLI operations，不做 HTTP API / UI
- [ ] 0.2 确认配置文件只保存 `credential_ref`，不保存真实 credential
- [ ] 0.3 确认本 change 不做 credential store / token rotation / secret manager
- [ ] 0.4 确认只保存最近一次 connector status，不做完整 run history
- [ ] 0.5 确认默认测试不访问真实 Google / Atlassian API

## 1. Connector config registry

- [ ] 1.1 Write failing tests: 可从 `settings.yaml` 读取 Google Drive connector 列表
- [ ] 1.2 Write failing tests: 可从 `settings.yaml` 读取 Confluence connector 列表
- [ ] 1.3 Write failing tests: `connector_id` 全局重复时 fail fast
- [ ] 1.4 Write failing tests: disabled connector 会出现在 list 中，但不可执行 sync
- [ ] 1.5 Write failing tests: 缺少必填字段时错误包含字段名
- [ ] 1.6 Implement: connector registry、typed config loading 和 validation
- [ ] 1.7 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_connector_operations.py -x -q`

## 2. Status store and migration

- [ ] 2.1 Write failing tests: Alembic upgrade 到 head 后包含 `knowledge_connector_status` 表
- [ ] 2.2 Write failing tests: never-run connector status 返回稳定 `never_run`
- [ ] 2.3 Write failing tests: 写入新 status 会覆盖同一 connector 的上一条 status
- [ ] 2.4 Write failing tests: status summary / error 会脱敏，不保存 token、secret 或 credential payload
- [ ] 2.5 Implement: status dataclasses、store API、Alembic migration 和 redaction
- [ ] 2.6 Verify green: 运行 `uv run pytest tests/integration/test_knowledge_connector_operations.py -x -q`

## 3. Credential and scope check

- [ ] 3.1 Write failing tests: credential_ref 文件缺失返回 `credential_missing`
- [ ] 3.2 Write failing tests: credential_ref env var 缺失返回 `credential_missing`
- [ ] 3.3 Write failing tests: credential payload 格式非法返回 `credential_invalid`
- [ ] 3.4 Write failing tests: fake client 认证失败返回 `auth_failed`
- [ ] 3.5 Write failing tests: remote scope 不可访问返回 `scope_unreachable`
- [ ] 3.6 Implement: `check_connector()` operation and sanitized result model
- [ ] 3.7 Verify green: 运行 `uv run pytest tests/unit/test_knowledge_connector_operations.py -x -q`

## 4. Dry-run and sync operations

- [ ] 4.1 Write failing tests: `run_connector_sync(dry_run=True)` 只生成 plan，不写 KB / source state / vector
- [ ] 4.2 Write failing tests: dry-run 结束后写入 `dry_run_ok` 或 `dry_run_failed` status
- [ ] 4.3 Write failing tests: `run_connector_sync(dry_run=False)` 调用对应 Google Drive / Confluence sync executor
- [ ] 4.4 Write failing tests: sync 成功后 status 包含 scanned / planned / ingested / changed / unchanged /
  unsupported / archived / failed / auth_failed summary
- [ ] 4.5 Write failing tests: sync 失败后 status 包含脱敏错误摘要，且不阻断 status 查询
- [ ] 4.6 Implement: dry-run / sync operation orchestration
- [ ] 4.7 Verify green: 运行 `uv run pytest tests/integration/test_knowledge_connector_operations.py -x -q`

## 5. Admin CLI

- [ ] 5.1 Write failing tests: `fleetent-admin kb connectors list` 输出配置 connector
- [ ] 5.2 Write failing tests: `fleetent-admin kb connectors check <connector_id>` 输出检查状态
- [ ] 5.3 Write failing tests: `fleetent-admin kb connectors status <connector_id>` 输出最近一次 status 或 never-run
- [ ] 5.4 Write failing tests: `fleetent-admin kb connectors sync <connector_id> --dry-run` 调用 dry-run operation
- [ ] 5.5 Write failing tests: `fleetent-admin kb connectors sync <connector_id>` 调用真实 sync operation
- [ ] 5.6 Write failing tests: CLI 输出不包含 credential payload、token、secret 或完整文档正文
- [ ] 5.7 Implement: admin CLI nested commands and output formatting
- [ ] 5.8 Verify green: 运行 `uv run pytest tests/unit/test_admin_cli.py -x -q`

## 6. Docs and final verification

- [ ] 6.1 更新 `config/settings.yaml.example`
- [ ] 6.2 更新 `docs/capabilities/knowledge-base.md`
- [ ] 6.3 更新 `docs/capabilities/deployment.md`
- [ ] 6.4 更新 `docs/capabilities/intelligence-roadmap.md`
- [ ] 6.5 更新 OpenSpec `configuration` / `knowledge-base` / `deployment` specs
- [ ] 6.6 运行 `uv run ruff format src tests`
- [ ] 6.7 运行 `uv run ruff check src tests`
- [ ] 6.8 运行 `uv run mypy src`
- [ ] 6.9 运行 `uv run pytest -x -q`
- [ ] 6.10 运行 `openspec validate 2026-06-02-knowledge-base-connector-operations --strict`
- [ ] 6.11 运行 `git diff --check`
