# diagnostics-redaction-export-hardening Specification

## Purpose
TBD - created by archiving change diagnostics-redaction-export-hardening. Update Purpose after archive.
## Requirements
### Requirement: Diagnostics manifest

Diagnostics export SHALL produce a manifest listing exported artifacts, skipped artifacts, redaction status,
creation time and source summary. 被跳过的 SQLite 库清单 SHALL 反映递归全树扫描的结果。

#### Scenario: Manifest lists skipped forbidden artifact
- **WHEN** diagnostics export omits a forbidden artifact such as a SQLite main database or secret file
- **THEN** the manifest records the skip reason without including the artifact contents

#### Scenario: Manifest 列出所有层级被跳过的库
- **WHEN** diagnostics export 在数据目录任意深度发现多个 SQLite 库
- **THEN** manifest 逐一记录每个被跳过的库（含子目录路径），不只记录顶层库

### Requirement: Default summary-only export

Diagnostics export SHALL NOT include secret payloads, SQLite main database files, backups, full prompt/reply
transcripts or KB document bodies by default. SQLite database 排除 SHALL 递归适用于数据目录全树——即持久层 #3 拆出的 per-tenant（`<tenant>/`）与 per-agent（`<tenant>/<agent_id>/`）子目录下的全部 `*.db`（管理库 / KB / 共享记忆 / per-agent 运行库 / 各向量库）及其 `-wal` / `-shm` sidecar，而非仅数据目录顶层文件。

#### Scenario: Secret file is not exported
- **WHEN** a configured secret file exists under the deployment secrets directory
- **THEN** diagnostics export excludes the file contents
- **AND** the manifest records only a redacted reference summary

#### Scenario: per-tenant 子目录库不被导出
- **WHEN** 数据目录下存在 `<tenant>/<agent_id>/agent_state.db`、`<tenant>/kb.db` 等子目录库（含 WAL sidecar）
- **THEN** diagnostics export 递归识别并排除这些库的内容，不因其位于子目录而被遗漏带出
- **AND** manifest 记录每个被跳过的库及跳过原因

### Requirement: Redacted evidence output

Diagnostics export SHALL redact token-like, credential-like and bearer values from config, trace and connector
summaries. Optional payload summary mode SHALL remain truncated and redacted.

#### Scenario: Trace payload summary is redacted
- **WHEN** safe payload summary mode is enabled
- **THEN** exported payload summaries are truncated and redacted
- **AND** raw transcript or KB document body is not exported

### Requirement: Agent home .env excluded from export and backup

由于 agent home 的 `.env` 现在含明文 secret（见 `node-secret-injection` 的 env-only 落盘），diagnostics 导出与任何打包/备份路径 SHALL 把 `<home>/agents/<name>/.env` 纳入排除清单——其内容 MUST NOT 出现在导出/备份产物中，manifest 仅记录一条 redacted 引用摘要（与既有 secret 文件、SQLite 主库的排除口径一致）。redaction 兜底 SHALL 覆盖 `.env` 形态的 `KEY=value` 明文值（token/credential/bearer 类），即使 `.env` 经其它路径被误带入摘要也被脱敏。

#### Scenario: agent .env 不被导出

- **WHEN** diagnostics export 扫描数据/home 目录时遇到 `<home>/agents/<name>/.env`
- **THEN** 导出 SHALL 排除其内容，manifest 仅记录 redacted 引用摘要
- **AND** 导出产物中不含该 `.env` 的任何明文 secret 值

#### Scenario: .env 形态值的 redaction 兜底

- **WHEN** 某 `.env` 风格的 `KEY=<token-like value>` 文本经任意路径进入导出摘要
- **THEN** 该值 SHALL 被脱敏（与 config/trace/connector 摘要中 token/credential/bearer 的 redaction 同口径）

