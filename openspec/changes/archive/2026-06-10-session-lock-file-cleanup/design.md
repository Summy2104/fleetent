## Context

`session/manager.py` 的 `session_lock()` 采用两层锁：跨进程 `fcntl.flock`（锚在 `{session_id}.lock` 文件）包住进程内 `asyncio.Lock`。flock 锚文件解锁时只 `LOCK_UN` + 关闭句柄、不删除文件——这是 flock 的标准做法，解锁时删文件存在经典竞态（另一进程可能已 open 旧 inode，删除后两个进程各持不同 inode 的"锁"）。

`cleanup_expired()` 删除过期 session 主文件后连带删除 `.pre-compact.json` / `.tool_outputs/` / `.resume` / `.todo`，但清单漏了 `.lock`，导致孤儿 `.lock` 永久残留。

## Goals / Non-Goals

**Goals:**
- 过期 session 清理时连带删除对应的 `.lock` 文件，杜绝孤儿残留

**Non-Goals:**
- 不改变 `session_lock()` 的加解锁语义（解锁时仍不删 `.lock`，避免竞态）
- 不清理存活 session 的 `.lock` 文件（它们是合法的 flock 锚）
- 不做存量孤儿 `.lock` 的一次性回扫（过期 session 的 `.lock` 会随本次改动在后续维护扫描中自然消除；主文件已不存在的历史孤儿不在 TTL 扫描覆盖内，数量有限且无害，不为此引入额外扫描路径）

## Decisions

**在 `cleanup_expired()` 删除主文件成功后连带删 `.lock`，而非在解锁路径删除。**
解锁时删除有 flock 竞态；而 TTL 清理时点 session 已过期（默认 30 天无活动），不存在并发持锁者，删除安全。即使极端情况下有进程恰好持有该 flock，flock 锁挂在 inode 上，删除路径名不影响已持有的锁，最坏结果是该进程解锁后文件重新出现，等下一轮清理。

**删除失败静默处理（`suppress(OSError)`），与 `.pre-compact.json` / `.resume` / `.todo` 一致。**
附属文件删除失败不应中断整批清理，也不值得 warn 日志。

**历史孤儿（主文件已删、仅剩 `.lock`）不回扫。**
TTL 扫描以 `*.json` 为锚，纯孤儿 `.lock` 无主文件可锚定。为其新增独立扫描路径的复杂度大于收益；运维可一次性手工清理存量。

## Risks / Trade-offs

- [极端竞态：清理删除 `.lock` 时恰有进程持有该 flock] → flock 挂 inode 不挂路径，已持有的锁不受影响；该进程后续解锁正常完成，仅文件可能被重建，下一轮清理兜底
- [本次改动不消除已有存量孤儿] → 接受；增量不再产生，存量无害且可手工清理
