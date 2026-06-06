## Context

`session_lock(session_id)` 是所有 session 写入路径（IM gateway、admin clear/reset/inject）的并发入口，目前实现：

```python
_locks: dict[str, asyncio.Lock] = {}

@asynccontextmanager
async def session_lock(session_id):
    async with _get_lock(session_id):
        yield
```

`asyncio.Lock` 是事件循环内的对象，只在单进程单事件循环内有效。跨进程场景（CLI + server、多 worker）无保护。

## Goals / Non-Goals

**Goals:**
- 同一 session 的写入在跨进程时也串行化
- 保持 `session_lock` 接口不变（调用方零改动）
- 锁文件不污染 session 扫描/清理逻辑
- 非 POSIX 平台优雅降级

**Non-Goals:**
- 不支持 NFS 跨主机锁（fleetent 用本地磁盘）
- 不实现锁超时/死锁检测（flock 在进程退出时自动释放，无孤儿锁问题）
- 不改造消息存储为 SQLite（属于更大的重构，不在本 change）

## Decisions

### D1：fcntl.flock 而非 filelock 库

见决策文档 D1。零依赖、POSIX 原生、本地磁盘可靠。

### D2：双层锁顺序——文件锁外层，asyncio 内层

```python
@asynccontextmanager
async def session_lock(session_id):
    lock_path = SESSIONS_DIR / f"{session_id}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if _flock_available:
        f = open(lock_path, "w")
        try:
            await asyncio.to_thread(fcntl.flock, f.fileno(), fcntl.LOCK_EX)
            async with _get_lock(session_id):
                yield
        finally:
            with suppress(Exception):
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
            f.close()
    else:
        async with _get_lock(session_id):
            yield
```

**关键点**：
- `fcntl.flock` 是阻塞调用，用 `asyncio.to_thread` 包装避免阻塞事件循环
- 文件锁在外层：跨进程粒度先于进程内粒度，避免「进程内拿到 asyncio 锁却卡在文件锁上」浪费
- `finally` 确保解锁 + 关闭文件句柄（flock 随 fd 关闭自动释放，双保险显式解锁）

### D3：锁文件不参与 TTL/容量/列举

`.lock` 是协调原语，不是数据。所有扫描 `*.json` 的地方天然不匹配 `.lock`（后缀不同），但需确认：
- `_scan_sessions()`：`rglob("*.json")` — `.lock` 不匹配，无需改
- `cleanup_expired()`：`rglob("*.json")` — 同上
- `list_session_ids()`：基于 `_scan_sessions()` — 同上

实际上 `.lock` 文件后缀天然被 `*.json` glob 排除。**唯一需要处理**：锁文件本身永不清理（长期残留空文件）。决策：锁文件极小（0 字节），常驻可接受；不主动清理避免与正在等锁的进程竞争。

### D4：平台降级

```python
try:
    import fcntl
    _flock_available = True
except ImportError:
    fcntl = None
    _flock_available = False
    _logger.warn("session_flock_unavailable_degraded_to_asyncio_lock")
```

非 POSIX（Windows）降级为仅 asyncio.Lock，行为与改动前一致。

## Risks / Trade-offs

- **[风险] 锁文件常驻磁盘** → 每 session 一个 0 字节 `.lock`，开销可忽略；不清理避免竞争
- **[风险] to_thread 包装 flock 增加开销** → 每次 session_lock 多一次线程切换；session 写入本身是 I/O 密集，开销相对可忽略
- **[风险] 同进程内同一 session 重入** → asyncio.Lock 不可重入，但现有代码无重入场景（session_lock 不嵌套调用自身）；flock 同 fd 可重入但不同 fd 间互斥——每次 session_lock 新开 fd，同进程两协程会在 asyncio 层先串行，不会同时到 flock，安全

## Migration Plan

无 schema 变更，无新依赖。部署即生效。已有 session 首次加锁时自动创建 `.lock` 文件。回滚：还原 session_lock 实现即可，`.lock` 文件残留无害。
