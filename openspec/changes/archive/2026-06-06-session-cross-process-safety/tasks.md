## 1. session_lock 双层锁实现

- [x] 1.1 Write failing unit tests for two-layer session_lock: 验证 session_lock 获取后创建 {session_id}.lock 文件；验证含 / 的 session_id 锁文件在子目录；验证退出后文件句柄关闭（可通过 patch fcntl.flock 断言 LOCK_EX 和 LOCK_UN 被调用）
- [x] 1.2 Write failing unit test for asyncio non-blocking: 验证 fcntl.flock 通过 asyncio.to_thread 调用（patch asyncio.to_thread 断言被调用）
- [x] 1.3 Add fcntl conditional import + _flock_available flag at module top: try import fcntl except ImportError → _flock_available=False + warn once
- [x] 1.4 Rewrite session_lock to two-layer: 文件锁外层（asyncio.to_thread(fcntl.flock, fd, LOCK_EX)）+ asyncio.Lock 内层；finally 释放锁+关闭句柄；非 POSIX 降级仅 asyncio.Lock

## 2. 锁文件不污染扫描/清理

- [x] 2.1 Write failing unit test for lock file exclusion: 创建 {sid}.lock 文件，验证 list_session_ids 和 _scan_sessions 不返回它；验证 cleanup_expired 不删除 .lock 文件
- [x] 2.2 Verify *.json glob excludes .lock: 确认 _scan_sessions/cleanup_expired/enforce_capacity 用 rglob("*.json")，.lock 天然排除（若有 *.lock 残留场景需显式跳过则补充）

## 3. 降级路径

- [x] 3.1 Write failing unit test for non-POSIX degradation: monkeypatch _flock_available=False，验证 session_lock 仍正常工作（仅 asyncio.Lock），不抛异常
- [x] 3.2 Verify degradation path works: 确认 _flock_available=False 时 session_lock 走纯 asyncio.Lock 分支

## 4. 收尾验证

- [x] 4.1 Run full test suite: uv run pytest tests/unit tests/integration -x -q
- [x] 4.2 Run test layer check: uv run python scripts/check_test_layers.py
- [x] 4.3 Run lint: uv run ruff format src tests && uv run ruff check src tests
