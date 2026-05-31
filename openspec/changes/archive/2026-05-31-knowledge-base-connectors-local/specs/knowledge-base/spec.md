## ADDED Requirements

### Requirement: Knowledge-base connector boundary
系统 SHALL 提供 DataSource / DocumentRef 边界，供不同文档来源接入 knowledge-base ingest。

#### Scenario: Connector API is importable
- **WHEN** 调用方导入 `DocumentRef` 和 `DataSource`
- **THEN** 导入成功

#### Scenario: DocumentRef shape
- **WHEN** connector 返回 `DocumentRef`
- **THEN** ref 包含 id、filename、format、path 或 url、metadata

### Requirement: Local directory data source
系统 SHALL 支持从显式允许的本地目录列举和读取文档。

#### Scenario: Local source only scans allowlisted root
- **WHEN** 配置 local directory source
- **THEN** connector 只读取该 root 下文件

#### Scenario: Path traversal is rejected
- **WHEN** 请求读取 allowlisted root 外的路径
- **THEN** 系统 fail fast

#### Scenario: Supported local formats
- **WHEN** local directory 包含 `.txt`、`.md`、`.html` 或 `.htm`
- **THEN** connector 返回对应 `DocumentRef`

#### Scenario: Unsupported local formats are skipped
- **WHEN** local directory 包含不支持后缀
- **THEN** connector 跳过该文件并在 sync summary 中体现

### Requirement: Local manual sync
系统 SHALL 提供手动 local directory sync，将支持的文件解析并导入指定 tenant/kb。

#### Scenario: Manual sync ingests supported files
- **WHEN** 调用 local sync API
- **THEN** 系统读取支持文件，调用 parser，并通过 core ingest 写入 KB

#### Scenario: Manual sync is tenant and kb scoped
- **WHEN** 同一目录同步到不同 tenant/kb
- **THEN** 文档和 chunks 写入对应 KB scope

#### Scenario: Manual sync returns summary
- **WHEN** local sync 完成
- **THEN** 返回 scanned、ingested、skipped、failed 等摘要计数

### Requirement: Local source state
系统 SHALL 记录本地文件状态，避免未变化文件重复 ingest。

#### Scenario: Unchanged files are skipped
- **WHEN** 文件 path、mtime 和 content hash 均未变化
- **THEN** 下一次 sync 不重复 ingest

#### Scenario: Changed files are reingested
- **WHEN** 文件内容 hash 变化
- **THEN** 下一次 sync 重新 ingest 该文件

### Requirement: Local connector excludes advanced sync
local connector SHALL NOT implement scheduler, Confluence, Google Drive, ACL enforcement or multi-worker
runtime.

#### Scenario: No scheduler dependency
- **WHEN** local sync 完成
- **THEN** 没有新增后台 scheduler 或 worker 进程要求
