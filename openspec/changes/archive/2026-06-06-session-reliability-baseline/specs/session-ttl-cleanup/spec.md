## MODIFIED Requirements

### Requirement: 过期 session 一次性清理

清理函数 `cleanup_expired()` SHALL 扫描 session 目录，删除所有过期 session 文件，并返回被删除的 session_id 列表。清理 MUST 不影响未过期的 session，MUST 不删除原子写产生的 `.json.tmp` 临时文件。清理成功删除文件后 MUST 同步删除 `sessions` 表中对应的 index 行；index 行删除失败 MUST 记录 warn 日志，MUST NOT 中断整批清理。

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
