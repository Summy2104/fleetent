## ADDED Requirements

### Requirement: Google Drive connector configuration
knowledge-base SHALL provide Google Drive connector configuration scoped to a target tenant and knowledge base.

#### Scenario: Google Drive connector config is importable
- **WHEN** 调用方从 knowledge-base public API 导入 Google Drive connector config
- **THEN** 导入成功

#### Scenario: Connector is scoped to tenant kb and folder
- **WHEN** 配置 Google Drive connector
- **THEN** config 包含 connector_id、tenant_id、kb_id、folder_id 和 OAuth credential_ref
- **AND** connector 只同步到指定 tenant_id + kb_id

#### Scenario: Connector uses OAuth user authorization
- **WHEN** connector 访问 Google Drive
- **THEN** 使用绑定到 connector 的 OAuth 用户授权
- **AND** 不要求 service account 或 domain-wide delegation

#### Scenario: OAuth credential belongs to connector
- **WHEN** 用户查询已同步 KB
- **THEN** 系统不使用该聊天用户的 Google Drive token 做实时过滤
- **AND** 已同步内容的访问控制由 KB scope 和后续 agent-KB binding 决定

#### Scenario: File based credential ref is supported
- **WHEN** Google Drive connector config 使用 file-based credential_ref
- **THEN** 系统可以从该引用加载 OAuth token
- **AND** 不要求新增 credential 表

### Requirement: Google Drive folder listing
Google Drive connector SHALL list documents from a configured folder scope instead of scanning the entire Drive.

#### Scenario: Folder scoped listing
- **WHEN** connector 运行 sync plan
- **THEN** 它只列举配置的 folder_id 范围内文档

#### Scenario: Unsupported MIME types are skipped
- **WHEN** folder 中包含 unsupported MIME type
- **THEN** planner 或 executor 跳过该文件
- **AND** summary 记录 unsupported 数量

#### Scenario: Auth failure is recorded
- **WHEN** OAuth token refresh 失败或 Drive API 返回授权失败
- **THEN** connector 标记为 `auth_failed`
- **AND** 不写入 KB documents、chunks 或 vector index

### Requirement: Google Drive content parsing
Google Drive connector SHALL map supported Drive content into existing knowledge-base parsers.

#### Scenario: Google Docs export uses HTML parser
- **WHEN** connector 同步 Google Docs
- **THEN** 它通过 Drive export API 导出 HTML
- **AND** 调用现有 HTML parser 生成 parsed document

#### Scenario: Plain text uses text parser
- **WHEN** connector 同步 plain text 文件
- **THEN** 它调用现有 text parser

#### Scenario: Markdown uses markdown parser
- **WHEN** connector 同步 Markdown 文件
- **THEN** 它调用现有 Markdown parser

#### Scenario: HTML file uses HTML parser
- **WHEN** connector 同步 HTML 文件
- **THEN** 它调用现有 HTML parser

#### Scenario: Google Sheets and Slides are unsupported in MVP
- **WHEN** connector 遇到 Google Sheets 或 Google Slides
- **THEN** 系统跳过该文件
- **AND** summary 记录 unsupported 数量

### Requirement: Google Drive sync planning
knowledge-base SHALL plan Google Drive sync actions before mutating KB documents, chunks, vector index, or source state.

#### Scenario: New Drive file is planned for ingest
- **WHEN** Drive folder 包含 supported file
- **AND** source state 中没有该 remote file
- **THEN** planner 生成 `ingest_new` item

#### Scenario: Changed Drive file is planned for reingest
- **WHEN** remote file modified time、revision 或 content hash 与 source state 不一致
- **THEN** planner 生成 `reingest_changed` item

#### Scenario: Unchanged Drive file is skipped
- **WHEN** remote file metadata 与 source state 一致
- **THEN** planner 生成 `skip_unchanged` item

#### Scenario: Missing Drive file is archived
- **WHEN** source state 中存在 remote file
- **AND** 当前 folder listing 不再包含该 file 或授权账号不再可见
- **THEN** planner 生成 `archive_missing` item
- **AND** 不生成 physical delete item

### Requirement: Google Drive sync execution
knowledge-base SHALL execute Google Drive sync plans through existing parser and KB public APIs.

#### Scenario: Execute ingest new
- **WHEN** executor 处理 Google Drive `ingest_new` item
- **THEN** 系统读取或 export 文件内容
- **AND** 调用 parser
- **AND** 调用 `ingest_parsed()` 写入指定 tenant_id + kb_id
- **AND** 成功后更新 source state

#### Scenario: Execute reingest changed
- **WHEN** executor 处理 Google Drive `reingest_changed` item
- **THEN** 系统更新对应 KB document / chunks
- **AND** 成功后更新 source state

#### Scenario: Execute archive missing
- **WHEN** executor 处理 `archive_missing` item
- **THEN** 系统标记对应 source / document 为 archived 或 missing
- **AND** 不调用 physical `delete(document_id)`
- **AND** 默认 search 不返回 archived document 的 chunks

#### Scenario: Per item failure isolation
- **WHEN** 某个 Google Drive plan item 执行失败
- **THEN** executor 记录 failed count
- **AND** 继续执行后续 item

### Requirement: Google Drive manual sync public API
knowledge-base SHALL expose manual Google Drive sync APIs that delegate to planner and executor.

#### Scenario: Google Drive sync API is importable
- **WHEN** 调用方从 knowledge-base public API 导入 `plan_google_drive_sync` 和 `sync_google_drive`
- **THEN** 导入成功

#### Scenario: Manual sync delegates to planner
- **WHEN** 调用 `sync_google_drive()`
- **THEN** 系统先生成 sync plan
- **AND** 再执行 plan
- **AND** 不边扫描边直接写 KB

#### Scenario: Manual sync returns summary
- **WHEN** Google Drive sync 完成
- **THEN** summary 包含 scanned、planned、ingested、changed、unchanged、unsupported、archived、failed 和 auth_failed 计数或状态

### Requirement: Google Drive connector tests avoid real API by default
Google Drive connector tests SHALL use fake clients by default and SHALL NOT connect to real Google APIs unless explicitly enabled.

#### Scenario: Default tests use fake Drive client
- **WHEN** 默认测试运行
- **THEN** 测试使用 fake Drive client / fixtures
- **AND** 不访问真实 Google API

#### Scenario: Real smoke requires explicit opt-in
- **WHEN** 未设置 `FLEETENT_GOOGLE_DRIVE_SMOKE=1`
- **THEN** Google Drive real smoke test 被 skip

#### Scenario: Real smoke skips without credentials
- **WHEN** 设置 `FLEETENT_GOOGLE_DRIVE_SMOKE=1` 但缺少 OAuth credential_ref 或 folder id
- **THEN** real smoke test 被 skip
