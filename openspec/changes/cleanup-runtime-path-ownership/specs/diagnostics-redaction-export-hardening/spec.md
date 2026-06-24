## MODIFIED Requirements

### Requirement: Default summary-only export

Diagnostics export SHALL NOT include secret payloads, SQLite main database files, backups, full prompt/reply
transcripts or KB document bodies by default. SQLite database 排除 SHALL 递归适用于扫描根全树：管理库、per-tenant KB、per-agent 运行库、各向量库及其 `-wal` / `-shm` sidecar 都必须排除，而非仅数据目录顶层文件。

Platform diagnostics 默认 export root SHALL be `FLEETENT_HOME/diagnostics/`. Agent runtime diagnostics 默认 export root SHALL be `<agent-home>/data/diagnostics/`. The default export root SHALL NOT be `FLEETENT_HOME/data/diagnostics/`.

#### Scenario: Secret file is not exported
- **WHEN** a configured secret file exists under the deployment secrets directory
- **THEN** diagnostics export excludes the file contents
- **AND** the manifest records only a redacted reference summary

#### Scenario: per-tenant 与 per-agent 库不被导出
- **WHEN** 扫描根下存在 `tenants/<tenant>/kb.db`、`tenants/<tenant>/agents/<agent>/data/agent_state.db` 等库（含 WAL sidecar）
- **THEN** diagnostics export 递归识别并排除这些库的内容，不因其位于子目录而被遗漏带出
- **AND** manifest 记录每个被跳过的库及跳过原因

#### Scenario: Platform diagnostics default is root-level
- **WHEN** platform/server 使用默认 diagnostics export 目录
- **THEN** export package 写入 `FLEETENT_HOME/diagnostics/`
- **AND** 不创建 `FLEETENT_HOME/data/diagnostics/`

#### Scenario: Agent diagnostics default is agent-scoped
- **WHEN** agent runtime 使用默认 diagnostics export 目录
- **THEN** export package 写入 `<agent-home>/data/diagnostics/`
- **AND** 不创建 `FLEETENT_HOME/data/diagnostics/`

### Requirement: Agent home .env excluded from export and backup

由于 agent home 的 `.env` 现在含明文 secret（见 `node-secret-injection` 的 env-only 落盘），diagnostics 导出与任何打包/备份路径 SHALL 把 `tenants/<tenant>/agents/<name>/.env` 纳入排除清单——其内容 MUST NOT 出现在导出/备份产物中，manifest 仅记录一条 redacted 引用摘要（与既有 secret 文件、SQLite 主库的排除口径一致）。redaction 兜底 SHALL 覆盖 `.env` 形态的 `KEY=value` 明文值（token/credential/bearer 类），即使 `.env` 经其它路径被误带入摘要也被脱敏。

#### Scenario: agent .env 不被导出

- **WHEN** diagnostics export 扫描 home 目录时遇到 `tenants/<tenant>/agents/<name>/.env`
- **THEN** 导出 SHALL 排除其内容，manifest 仅记录 redacted 引用摘要
- **AND** 导出产物中不含该 `.env` 的任何明文 secret 值

#### Scenario: .env 形态值的 redaction 兜底

- **WHEN** 某 `.env` 风格的 `KEY=<token-like value>` 文本经任意路径进入导出摘要
- **THEN** 该值 SHALL 被脱敏（与 config/trace/connector 摘要中 token/credential/bearer 的 redaction 同口径）
