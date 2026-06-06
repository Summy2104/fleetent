## ADDED Requirements

### Requirement: 跨进程文件锁串行化同一 session 写入

`session_lock(session_id)` SHALL 在进程内 `asyncio.Lock` 之外，使用基于 `fcntl.flock()` 的文件级排他锁实现跨进程串行化。锁文件路径为 `data/sessions/{session_id}.lock`。锁的获取顺序 MUST 为：先获取文件锁（跨进程），再获取 asyncio.Lock（进程内）；退出时 MUST 释放文件锁并关闭文件句柄。

#### Scenario: 跨进程写入串行化
- **WHEN** 两个不同进程同时对同一 `session_id` 调用 `session_lock`
- **THEN** 后获取者阻塞，直到先获取者退出 `session_lock` 上下文释放文件锁

#### Scenario: 锁文件路径支持含斜杠 session_id
- **WHEN** session_id 含 `/`（如 IM 平台格式 `slack:C1/U2`）
- **THEN** 锁文件在对应子目录创建（`data/sessions/slack:C1/U2.lock`），不报错

#### Scenario: 退出时释放文件锁
- **WHEN** `session_lock` 上下文正常退出或因异常退出
- **THEN** 文件锁被释放，文件句柄被关闭，其他等待进程可获取

### Requirement: 文件锁阻塞调用不阻塞事件循环

`fcntl.flock` 是阻塞系统调用，获取文件锁 MUST 通过 `asyncio.to_thread` 包装，避免阻塞 asyncio 事件循环。

#### Scenario: 获取文件锁不冻结事件循环
- **WHEN** 一个协程在 `session_lock` 中等待文件锁
- **THEN** 同进程其他协程（处理不同 session）仍可正常运行，事件循环不被阻塞

### Requirement: 非 POSIX 平台降级为进程内锁

系统 SHALL 在 `fcntl` 不可用的平台（如 Windows）降级为仅使用进程内 `asyncio.Lock`，并在模块加载时记录一次 warn 日志。降级后 `session_lock` 接口与行为对调用方保持兼容。

#### Scenario: fcntl 不可用时降级
- **WHEN** 运行平台不支持 `fcntl`（导入失败）
- **THEN** `session_lock` 仅使用 asyncio.Lock，记录一次降级 warn 日志，不抛出异常

### Requirement: 锁文件不纳入 session 数据扫描

`.lock` 锁文件 MUST NOT 被 `_scan_sessions`、`cleanup_expired`、`enforce_capacity`、`list_session_ids` 当作 session 数据文件处理（这些函数扫描 `*.json`，`.lock` 后缀天然排除）。锁文件 MUST NOT 被 TTL 或容量清理删除。

#### Scenario: 锁文件不被当作 session
- **WHEN** session 目录中存在 `{session_id}.lock` 文件
- **THEN** `list_session_ids()` 和 `_scan_sessions()` 不返回该锁文件对应的条目

#### Scenario: 锁文件不被 TTL 清理删除
- **WHEN** `cleanup_expired()` 扫描 session 目录
- **THEN** `.lock` 文件不被纳入过期判定或删除
