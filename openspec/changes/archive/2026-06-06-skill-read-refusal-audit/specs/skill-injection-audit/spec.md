## ADDED Requirements

### Requirement: read_skill 拒绝 audit_blocked skill 时写审计日志

当 `read_skill(name)` 因 skill 被标记 `audit_blocked` 而返回拒绝文本时，MUST 写一条审计日志记录该拒绝事件。审计日志 SHALL 含 action `skill.read_refused`、target 为该 skill 名、detail 含拒绝原因（`audit_blocked`）以及可得的 `session_id` / `agent_name`（来自 out-of-band 注入的 tool context，缺失则为 null）。

审计写入失败 MUST NOT 改变拒绝行为：write_audit 抛异常时 SHALL 捕获并记录告警，`read_skill` 仍返回拒绝文本（拒绝是安全核心，不因旁路审计失败而退化）。

正常读取路径（skill 未被 audit_blocked）MUST NOT 写该审计日志。

#### Scenario: 拒绝时写审计日志

- **WHEN** 对一个 `audit_blocked` 的 skill 调用 `read_skill`
- **THEN** 返回拒绝文本（不返回正文）
- **AND** 写一条 action 为 `skill.read_refused`、target 为该 skill 名的审计日志

#### Scenario: 审计含 session/agent 上下文

- **WHEN** `read_skill` 在带 tool context（session_id / agent_name）的执行环境下拒绝一个 audit_blocked skill
- **THEN** 审计日志 detail 含该 session_id 与 agent_name

#### Scenario: 正常读取不写拒绝日志

- **WHEN** 对一个未被 audit_blocked 的 skill 调用 `read_skill`
- **THEN** 返回其 SKILL.md 正文
- **AND** 不写 `skill.read_refused` 审计日志

#### Scenario: 审计写入失败不阻断拒绝

- **WHEN** `read_skill` 拒绝一个 audit_blocked skill 但审计写入抛异常
- **THEN** 异常被捕获并记录告警
- **AND** `read_skill` 仍返回拒绝文本
