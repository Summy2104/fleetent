## 0. 前置确认

- [x] 0.1 确认默认不设置 retention 时长
- [x] 0.2 确认默认不自动清理，`diagnostics.retention.enabled=false`
- [x] 0.3 确认 retention 只处理诊断数据，不处理业务数据
- [x] 0.4 确认本 change 不做 scheduler 自动清理
- [x] 0.5 确认本 change 不删除 SQLite backups

## 1. Diagnostics config

- [x] 1.1 Write failing tests: `Settings()` 默认包含 `diagnostics.export_dir="data/diagnostics"`
- [x] 1.2 Write failing tests: `Settings()` 默认 `diagnostics.retention.enabled=false`
- [x] 1.3 Write failing tests: logs / traces / diagnostic_exports retention days 默认为空
- [x] 1.4 Write failing tests: `enabled=true` 但某个 days 字段为空时，该类型不清理
- [x] 1.5 Implement: diagnostics settings dataclasses and YAML example
- [x] 1.6 Verify green: 运行 `uv run pytest tests/unit/test_config.py -x -q`

## 2. Diagnostics export

- [x] 2.1 Write failing tests: `export_diagnostics()` 生成 zip 包和 `manifest.json`
- [x] 2.2 Write failing tests: export 包含指定时间范围内的 structured logs
- [x] 2.3 Write failing tests: export 包含 trace events 或 trace summary、usage summary 和 performance summary
- [x] 2.4 Write failing tests: export 包含 connector status summary
- [x] 2.5 Write failing tests: export 包含 environment summary 和 config summary
- [x] 2.6 Write failing tests: export 不包含 memory 内容、KB 正文 / chunks、SQLite 主库或 SQLite backups
- [x] 2.7 Write failing tests: export 对 token、secret、邮箱、手机号、credential payload 和大文本做脱敏 / 截断
- [x] 2.8 Implement: diagnostics export API and package writer
- [x] 2.9 Verify green: 运行 `uv run pytest tests/unit/test_diagnostics_export.py -x -q`

## 3. Retention planning

- [x] 3.1 Write failing tests: retention dry-run 识别超过 `logs_days` 的日志文件
- [x] 3.2 Write failing tests: retention dry-run 识别超过 `traces_days` 的 trace 记录数量
- [x] 3.3 Write failing tests: retention dry-run 识别超过 `diagnostic_exports_days` 的 export 包
- [x] 3.4 Write failing tests: days 字段为空时不产生该类型删除候选
- [x] 3.5 Write failing tests: dry-run 不删除文件、不删除 trace 记录
- [x] 3.6 Implement: retention plan dataclasses and dry-run logic
- [x] 3.7 Verify green: 运行 `uv run pytest tests/unit/test_diagnostics_retention.py -x -q`

## 4. Retention apply

- [x] 4.1 Write failing tests: `diagnostics.retention.enabled=false` 时 apply fail fast
- [x] 4.2 Write failing tests: enabled 且设置 `logs_days` 时只删除过期 logs
- [x] 4.3 Write failing tests: enabled 且设置 `traces_days` 时只删除过期 traces
- [x] 4.4 Write failing tests: enabled 且设置 `diagnostic_exports_days` 时只删除过期 export 包
- [x] 4.5 Write failing tests: apply 不删除 memory、KB、vector index、connector source state、SQLite 主库或 backups
- [x] 4.6 Write failing tests: 单个文件删除失败时记录失败并继续处理其他候选
- [x] 4.7 Implement: retention apply logic
- [x] 4.8 Verify green: 运行 `uv run pytest tests/integration/test_diagnostics_retention.py -x -q`

## 5. Admin CLI

- [x] 5.1 Write failing tests: `fleetent-admin diagnostics export` 调用 export API 并输出包路径
- [x] 5.2 Write failing tests: `fleetent-admin diagnostics retention dry-run` 输出候选摘要且不删除
- [x] 5.3 Write failing tests: `fleetent-admin diagnostics retention apply` 在 disabled 时返回非 0
- [x] 5.4 Write failing tests: CLI 输出不包含 token、secret、credential payload 或完整文档正文
- [x] 5.5 Implement: admin CLI diagnostics commands
- [x] 5.6 Verify green: 运行 `uv run pytest tests/unit/test_admin_cli.py -x -q`

## 6. Docs and final verification

- [x] 6.1 更新 `config/settings.yaml.example`
- [x] 6.2 更新 `docs/capabilities/observability.md`
- [x] 6.3 更新 `docs/capabilities/deployment.md`
- [x] 6.4 更新 `docs/capabilities/intelligence-roadmap.md`
- [x] 6.5 更新 OpenSpec `configuration` / `observability` / `deployment` specs
- [x] 6.6 运行 `uv run ruff format src tests`
- [x] 6.7 运行 `uv run ruff check src tests`
- [x] 6.8 运行 `uv run mypy src`
- [x] 6.9 运行 `uv run pytest -x -q`
- [x] 6.10 运行 `openspec validate 2026-06-02-data-retention-and-diagnostics-policy --strict`
- [x] 6.11 运行 `git diff --check`
