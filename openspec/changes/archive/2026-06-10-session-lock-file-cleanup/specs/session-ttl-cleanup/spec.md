## MODIFIED Requirements

### Requirement: 过期 session 一次性清理

清理函数 `cleanup_expired()` SHALL 扫描 session 目录，删除所有过期 session 文件，并返回被删除的 session_id 列表。清理 MUST 不影响未过期的 session，MUST 不删除原子写产生的 `.json.tmp` 临时文件，MUST 不将 `.pre-compact.json` 备份文件纳入过期判定（备份文件跟随主文件删除，不独立判断 TTL），MUST 跳过路径含 `.tool_outputs/` 的外部化 tool result 文件（不当作 session）。清理成功删除主文件后 MUST 同步删除对应的 `.pre-compact.json` 备份文件（若存在）、`{session_id}.tool_outputs` 外部目录（若存在）、`{session_id}.todo` 任务列表文件（若存在）以及 `{session_id}.lock` flock 锚文件（若存在），备份、外部目录、任务列表与锚文件删除失败静默处理。清理成功删除文件后 MUST 同步删除 `sessions` 表中对应的 index 行；index 行删除失败 MUST 记录 warn 日志，MUST NOT 中断整批清理。

#### Scenario: 清理跳过备份文件的过期判定
- **WHEN** `cleanup_expired()` 扫描 session 目录时遇到 `.pre-compact.json` 文件
- **THEN** 该文件不被纳入 TTL 过期判定，不被直接删除

#### Scenario: 清理主文件时同步删除备份文件
- **WHEN** `cleanup_expired()` 成功删除某 session 的主文件 `{session_id}.json`
- **THEN** 对应的 `{session_id}.pre-compact.json` 若存在则被同步删除

#### Scenario: 备份文件删除失败静默处理
- **WHEN** 主文件删除成功但备份文件删除失败
- **THEN** 失败被静默处理，不记录 warn 日志，不中断清理批次

#### Scenario: 清理主文件时连带删除外部 tool 目录
- **WHEN** `cleanup_expired()` 成功删除某 session 的主文件，且该 session 有 `.tool_outputs` 目录
- **THEN** 对应的 `{session_id}.tool_outputs` 目录被连带删除

#### Scenario: 清理主文件时连带删除 todo 文件
- **WHEN** `cleanup_expired()` 成功删除某 session 的主文件，且该 session 有 `{session_id}.todo` 文件
- **THEN** 对应的 `{session_id}.todo` 文件被连带删除（删除失败静默处理）

#### Scenario: 清理主文件时连带删除 lock 锚文件
- **WHEN** `cleanup_expired()` 成功删除某 session 的主文件，且该 session 有 `{session_id}.lock` 文件
- **THEN** 对应的 `{session_id}.lock` 文件被连带删除（删除失败静默处理）

#### Scenario: 存活 session 的 lock 锚文件不受清理影响
- **WHEN** `cleanup_expired()` 执行时存在未过期 session 及其 `{session_id}.lock` 文件
- **THEN** 该 `.lock` 文件保留不删除

#### Scenario: 清理跳过 tool_outputs 内文件
- **WHEN** `cleanup_expired()` 扫描时遇到 `.tool_outputs/` 目录内的文件
- **THEN** 这些文件不被当作 session 纳入过期判定

#### Scenario: 外部目录删除失败静默处理
- **WHEN** 主文件删除成功但 `.tool_outputs` 目录删除失败
- **THEN** 失败被静默处理，不中断清理批次

#### Scenario: 清理删除过期文件并返回列表
- **WHEN** 调用 `cleanup_expired()` 且目录中存在过期与未过期 session
- **THEN** 仅过期 session 文件被删除，未过期 session 文件保留，返回值为被删除的 session_id 列表

#### Scenario: 清理同步删除索引行
- **WHEN** `cleanup_expired()` 成功删除若干过期 session 文件
- **THEN** `sessions` 表中对应的 session_id 行被同步删除，后续 `count()` 和 `list_by_user()` 不再返回这些 session

#### Scenario: 索引删除失败不中断清理
- **WHEN** 文件删除成功但 `sessions` 表的 index 行删除抛出异常
- **THEN** 该异常被记录为 warn 日志，整批清理继续，不回滚已删除的文件

#### Scenario: 不误删临时文件
- **WHEN** 清理时目录中存在原子写中间态 `.json.tmp` 文件
- **THEN** 该 `.json.tmp` 文件不被清理函数删除

#### Scenario: 带斜杠的 session_id 在子目录中被正确清理
- **WHEN** 过期 session 的 session_id 含 `/`（文件位于子目录）
- **THEN** 该子目录中的过期文件被删除，返回的 session_id 还原为含 `/` 的原始标识
