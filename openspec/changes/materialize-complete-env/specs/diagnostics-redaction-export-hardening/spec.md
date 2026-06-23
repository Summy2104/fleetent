## ADDED Requirements

### Requirement: Agent home .env excluded from export and backup

由于 agent home 的 `.env` 现在含明文 secret（见 `node-secret-injection` 的 env-only 落盘），diagnostics 导出与任何打包/备份路径 SHALL 把 `<home>/agents/<name>/.env` 纳入排除清单——其内容 MUST NOT 出现在导出/备份产物中，manifest 仅记录一条 redacted 引用摘要（与既有 secret 文件、SQLite 主库的排除口径一致）。redaction 兜底 SHALL 覆盖 `.env` 形态的 `KEY=value` 明文值（token/credential/bearer 类），即使 `.env` 经其它路径被误带入摘要也被脱敏。

#### Scenario: agent .env 不被导出

- **WHEN** diagnostics export 扫描数据/home 目录时遇到 `<home>/agents/<name>/.env`
- **THEN** 导出 SHALL 排除其内容，manifest 仅记录 redacted 引用摘要
- **AND** 导出产物中不含该 `.env` 的任何明文 secret 值

#### Scenario: .env 形态值的 redaction 兜底

- **WHEN** 某 `.env` 风格的 `KEY=<token-like value>` 文本经任意路径进入导出摘要
- **THEN** 该值 SHALL 被脱敏（与 config/trace/connector 摘要中 token/credential/bearer 的 redaction 同口径）
