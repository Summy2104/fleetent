## MODIFIED Requirements

### Requirement: Document import via multiple entry points

An admin SHALL import documents by pasting / uploading text, Markdown, or lightweight HTML, and by configuring a local directory data source and manually triggering sync. The management plane SHALL enqueue execute-path ingest work via `kb-ingest-queue` before consuming it; it SHALL NOT keep the old direct `asyncio.run(...)` execute path in the route handler.

#### Scenario: Paste import enqueues before execution

- **WHEN** an admin pastes text/markdown/html content into a KB on a running local server
- **THEN** the system first enqueues a `kb_ingest_jobs` record for that import
- **AND** in the current transition phase it may consume that same job inline and return the real document id, chunk count, filename/source metadata

#### Scenario: Local directory sync enqueues before execution

- **WHEN** an admin configures a local directory source and triggers sync
- **THEN** the system first enqueues a `kb_ingest_jobs` record for that sync
- **AND** in the current transition phase it may consume that same job inline and return scanned / ingested / skipped / failed counts

#### Scenario: Full re-sync requires confirmation

- **WHEN** an admin triggers a full directory re-sync
- **THEN** the action requires a second confirmation and is audited (`doc_sync`)

## ADDED Requirements

### Requirement: Connector sync 经队列异步执行

`kb_admin_api` 的 connector sync SHALL 经 `kb-ingest-queue` 入队执行。dry-run(仅出 plan、不写)可保持同步;execute(真实写)SHALL 先入队,再由当前过渡 drain 或后续 worker 消费。

#### Scenario: Execute sync 入队

- **WHEN** admin 调用 connector sync(execute,非 dry-run)
- **THEN** 端点先写入一条 ingest job
- **AND** 返回 job id(或入队+等完成的结果),而不是沿用旧的直连 execute 路径

#### Scenario: Dry-run 仍同步出 plan

- **WHEN** admin 调用 connector sync `--dry-run`
- **THEN** 端点同步返回 plan summary(不写、不入 execute 队列)

#### Scenario: 输出仍脱敏

- **WHEN** 端点返回 sync / 入队结果
- **THEN** 输出不含 token、secret、credential payload 或完整文档正文
