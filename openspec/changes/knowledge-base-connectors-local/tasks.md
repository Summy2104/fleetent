## 0. 前置确认

- [x] 0.1 确认 `knowledge-base-core` 和 `knowledge-base-parsers-basic` 已完成
- [x] 0.2 确认本 change 不实现 scheduler、Confluence、Google Drive、ACL 或多 worker
- [x] 0.3 确认测试只使用 `tmp_path`

## 1. DataSource boundary

- [x] 1.1 Write failing tests: `DocumentRef` 和 `DataSource` 可导入
- [x] 1.2 Write failing tests: `DocumentRef` 包含 id、filename、format、path/url、metadata
- [x] 1.3 实现 connector boundary
- [x] 1.4 运行 `uv run pytest tests/unit -x -q`

## 2. Local directory listing and fetching

- [x] 2.1 Write failing tests: local data source 只扫描配置 allowlist root 下文件
- [x] 2.2 Write failing tests: 支持 `.txt`、`.md`、`.html` / `.htm` 格式映射
- [x] 2.3 Write failing tests: fetch 读取文件内容并保留 path metadata
- [x] 2.4 实现 local directory connector
- [x] 2.5 运行 `uv run pytest tests/unit -x -q`

## 3. Source state and duplicate avoidance

- [x] 3.1 Write failing tests: sync 记录 source path、mtime、content hash
- [x] 3.2 Write failing tests: 未变化文件不会重复 ingest
- [x] 3.3 Write failing tests: 内容变化文件会重新 ingest
- [x] 3.4 实现 source state store / migration
- [x] 3.5 运行 `uv run pytest tests/integration -x -q`

## 4. Manual sync

- [x] 4.1 Write failing tests: manual sync 调用 parser + ingest，把本地文档导入指定 tenant/kb
- [x] 4.2 Write failing tests: unsupported extension 被跳过并返回 summary
- [x] 4.3 Write failing tests: root 越界路径 fail fast
- [x] 4.4 实现 manual sync API
- [x] 4.5 运行 `uv run pytest tests/integration -x -q`

## 5. Docs and verification

- [x] 5.1 更新 `docs/capabilities/knowledge-base.md`
- [x] 5.2 运行 `uv run pytest -x -q`
- [x] 5.3 运行 `uv run ruff format src tests`
- [x] 5.4 运行 `uv run ruff check src tests`
- [x] 5.5 运行 `uv run mypy src`
- [x] 5.6 运行 `openspec validate knowledge-base-connectors-local`
