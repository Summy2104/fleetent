## ADDED Requirements

### Requirement: Confluence connector configuration
knowledge-base SHALL provide Confluence connector configuration scoped to a target tenant and knowledge base.

#### Scenario: Confluence connector config is importable
- **WHEN** 调用方从 knowledge-base public API 导入 Confluence connector config
- **THEN** 导入成功

#### Scenario: Connector is scoped to tenant kb and Confluence scope
- **WHEN** 配置 Confluence connector
- **THEN** config 包含 connector_id、tenant_id、kb_id、base_url、username 和 API token credential_ref
- **AND** config 包含 space scope、page scope 或 page include_children scope
- **AND** connector 只同步到指定 tenant_id + kb_id

#### Scenario: Connector uses Confluence Cloud API token
- **WHEN** connector 访问 Confluence
- **THEN** 使用绑定到 connector 的 Confluence Cloud username + API token credential
- **AND** 不要求 Server / Data Center、Basic Auth 或 PAT 分支

#### Scenario: Confluence credential belongs to connector
- **WHEN** 用户查询已同步 KB
- **THEN** 系统不使用该聊天用户的 Confluence credential 做实时过滤
- **AND** 已同步内容的访问控制由 KB scope 和后续 agent-KB binding 决定

### Requirement: Confluence scope listing
Confluence connector SHALL list pages from configured scopes instead of scanning the entire site.

#### Scenario: Space scope lists pages
- **WHEN** connector 配置 space_key
- **THEN** planner 只列举该 space 中 pages

#### Scenario: Page scope lists one page
- **WHEN** connector 配置 page_id 且 include_children=false
- **THEN** planner 只列举该 page

#### Scenario: Page children scope lists descendants
- **WHEN** connector 配置 page_id 且 include_children=true
- **THEN** planner 列举该 page 及 descendant pages

#### Scenario: Auth failure is recorded
- **WHEN** API token 无效、权限不足或 Confluence API 返回授权失败
- **THEN** connector 标记为 `auth_failed`
- **AND** 不写入 KB documents、chunks 或 vector index

### Requirement: Confluence page parsing
Confluence connector SHALL fetch page storage HTML and map it into existing knowledge-base parsers.

#### Scenario: Page fetch expands required fields
- **WHEN** connector 拉取 Confluence page
- **THEN** 请求包含 storage HTML、version、space 和 ancestors 信息

#### Scenario: Storage HTML uses HTML parser
- **WHEN** connector 同步 Confluence page
- **THEN** 它调用现有 HTML parser 生成 parsed document

#### Scenario: Page metadata is preserved
- **WHEN** connector 同步 Confluence page
- **THEN** parsed metadata 包含 page id、title、space key、ancestors 或 path text

### Requirement: Confluence sync planning
knowledge-base SHALL plan Confluence sync actions before mutating KB documents, chunks, vector index, or source state.

#### Scenario: New page is planned for ingest
- **WHEN** Confluence scope 包含 page
- **AND** source state 中没有该 page
- **THEN** planner 生成 `ingest_new` item

#### Scenario: Changed page is planned for reingest
- **WHEN** page version 或 modified time 与 source state 不一致
- **THEN** planner 生成 `reingest_changed` item

#### Scenario: Unchanged page is skipped
- **WHEN** page metadata 与 source state 一致
- **THEN** planner 生成 `skip_unchanged` item

#### Scenario: Missing page is archived
- **WHEN** source state 中存在 page
- **AND** 当前 scope listing 不再包含该 page 或 credential 不再可见
- **THEN** planner 生成 `archive_missing` item
- **AND** 不生成 physical delete item

### Requirement: Confluence sync execution
knowledge-base SHALL execute Confluence sync plans through existing parser and KB public APIs.

#### Scenario: Execute ingest new
- **WHEN** executor 处理 Confluence `ingest_new` item
- **THEN** 系统读取 page storage HTML
- **AND** 调用 HTML parser
- **AND** 调用 `ingest_parsed()` 写入指定 tenant_id + kb_id
- **AND** 成功后更新 source state

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 Confluence `reingest_changed` item
- **THEN** 系统更新对应 KB document / chunks
- **AND** 成功后更新 source state

#### Scenario: Execute archive missing
- **WHEN** executor 处理 `archive_missing` item
- **THEN** 系统标记对应 source / document 为 archived 或 missing
- **AND** 不调用 physical `delete(document_id)`
- **AND** 默认 search 不返回 archived document 的 chunks

#### Scenario: Per item failure isolation
- **WHEN** 某个 Confluence plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 item

### Requirement: Confluence rate limit and retry
Confluence connector SHALL tolerate basic rate limiting without failing the entire sync.

#### Scenario: Retry after rate limit
- **WHEN** Confluence API 返回 429 和 Retry-After
- **THEN** connector 等待 Retry-After 后重试该请求

#### Scenario: Retry exhaustion records failure
- **WHEN** 请求超过重试上限
- **THEN** 当前 item 记录 failed
- **AND** 后续 item 继续执行

### Requirement: Confluence manual sync public API
knowledge-base SHALL expose manual Confluence sync APIs that delegate to planner and executor.

#### Scenario: Confluence sync API is importable
- **WHEN** 调用方从 knowledge-base public API 导入 `plan_confluence_sync` 和 `sync_confluence`
- **THEN** 导入成功

#### Scenario: Manual sync delegates to planner
- **WHEN** 调用 `sync_confluence()`
- **THEN** 系统先生成 sync plan
- **AND** 再执行 plan
- **AND** 不边扫描边直接写 KB

#### Scenario: Manual sync returns summary
- **WHEN** Confluence sync 完成
- **THEN** summary 包含 scanned、planned、ingested、changed、unchanged、archived、failed 和 auth_failed 计数或状态

### Requirement: Confluence connector tests avoid real API by default
Confluence connector tests SHALL use fake clients by default and SHALL NOT connect to real Confluence unless explicitly enabled.

#### Scenario: Default tests use fake Confluence client
- **WHEN** 默认测试运行
- **THEN** 测试使用 fake Confluence client / fixtures
- **AND** 不访问真实 Confluence

#### Scenario: Real smoke requires explicit opt-in
- **WHEN** 未设置 `FLEETENT_CONFLUENCE_SMOKE=1`
- **THEN** Confluence real smoke test 被 skip

#### Scenario: Real smoke skips without credentials
- **WHEN** 设置 `FLEETENT_CONFLUENCE_SMOKE=1` 但缺少 base URL、username、credential_ref 或 scope
- **THEN** real smoke test 被 skip
