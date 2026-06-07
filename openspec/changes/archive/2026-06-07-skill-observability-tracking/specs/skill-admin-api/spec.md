## ADDED Requirements

### Requirement: Skill 命中追踪提供真实 observability 数据

每次 `read_skill` 成功加载一个 skill 的全文 MUST 记录一条命中（skill 名、可得的 agent / session、时间戳）到持久化存储。per-skill observability 查询 MUST 据此返回真实数据——命中计数与触发它的去重 session 列表，且 `stale` MUST 为假——而非固定的空占位符。

命中记录 MUST 为 best-effort：记录写入失败（DB 不可用等）SHALL 被捕获并记录告警，MUST NOT 阻断 `read_skill` 返回 skill 正文。被拒绝（audit_blocked）或未知名的 read_skill 调用 MUST NOT 记为命中。

#### Scenario: read_skill 成功加载记一次命中

- **WHEN** 对一个可用 skill 成功调用 `read_skill`
- **THEN** 存储中新增一条该 skill 的命中记录（含可得的 agent/session 与时间戳）

#### Scenario: observability 返回真实命中与 session

- **WHEN** 某 skill 已被 read_skill 加载若干次（来自不同 session），admin 查询其 observability
- **THEN** 返回真实命中计数与触发它的去重 session 列表，`stale` 为假

#### Scenario: 命中记录失败不阻断 read_skill

- **WHEN** `read_skill` 成功加载 skill 但命中记录写入抛异常
- **THEN** 异常被捕获并记录告警，`read_skill` 仍返回 skill 正文

#### Scenario: 拒绝与未知名不记命中

- **WHEN** `read_skill` 因 audit_blocked 被拒，或因未知 skill 名返回错误
- **THEN** 不记录命中
