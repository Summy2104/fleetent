## ADDED Requirements

### Requirement: 基于最后活跃时间的 TTL 过期判定

session 清理 SHALL 以 session 文件的最后活跃时间（文件 mtime）判定是否过期；当 `now - 最后活跃时间` 超过配置的 TTL 时，该 session MUST 被判定为过期。过期判定 MUST 使用最后活跃时间而非创建时间。

#### Scenario: 超过 TTL 的 session 判定为过期
- **WHEN** 某 session 文件的最后活跃时间早于 `now - TTL`
- **THEN** 该 session 被判定为过期，进入待清理集合

#### Scenario: 未超过 TTL 的 session 不过期
- **WHEN** 某 session 文件的最后活跃时间晚于 `now - TTL`
- **THEN** 该 session 不被判定为过期，保留不删除

### Requirement: 过期 session 一次性清理

清理函数 `cleanup_expired()` SHALL 扫描 session 目录，删除所有过期 session 文件，并返回被删除的 session_id 列表。清理 MUST 不影响未过期的 session，MUST 不删除原子写产生的 `.json.tmp` 临时文件。

#### Scenario: 清理删除过期文件并返回列表
- **WHEN** 调用 `cleanup_expired()` 且目录中存在过期与未过期 session
- **THEN** 仅过期 session 文件被删除，未过期 session 文件保留，返回值为被删除的 session_id 列表

#### Scenario: 不误删临时文件
- **WHEN** 清理时目录中存在原子写中间态 `.json.tmp` 文件
- **THEN** 该 `.json.tmp` 文件不被清理函数删除

#### Scenario: 带斜杠的 session_id 在子目录中被正确清理
- **WHEN** 过期 session 的 session_id 含 `/`（文件位于子目录）
- **THEN** 该子目录中的过期文件被删除，返回的 session_id 还原为含 `/` 的原始标识

### Requirement: TTL 时长可配置与覆盖

TTL 时长 SHALL 来自 `Settings.session_ttl_days`（env 可配，默认 30 天）。`cleanup_expired()` MUST 接受可选 TTL 参数；当显式传入时，该参数 MUST 覆盖 Settings 配置值。

#### Scenario: 使用 Settings 默认 TTL
- **WHEN** 调用 `cleanup_expired()` 未传 TTL 参数
- **THEN** 使用 `Settings.session_ttl_days` 对应的 TTL 秒数进行过期判定

#### Scenario: 调用参数覆盖配置
- **WHEN** 调用 `cleanup_expired()` 时显式传入 TTL 参数
- **THEN** 过期判定使用传入的 TTL，而非 Settings 配置值

### Requirement: 删除容错与日志记录

清理过程 SHALL 对单个文件的删除失败容错；某个文件删除失败时 MUST 不中断整批清理，MUST 记录警告日志后继续处理其余文件。清理操作 MUST 记录在系统日志中。

#### Scenario: 单个删除失败不中断整批
- **WHEN** 清理过程中某个过期文件删除失败（如已被并发删除）
- **THEN** 该失败被记录为警告日志，清理继续处理其余过期文件，不抛出异常中断整批

#### Scenario: 清理操作写入系统日志
- **WHEN** 清理函数执行并删除了过期 session
- **THEN** 系统日志记录被清理的 session 及清理汇总信息
