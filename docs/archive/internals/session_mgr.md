# session_mgr.py

## 职责

跨请求的会话持久化：把消息历史写到磁盘，下次请求时恢复。每个 session_id 对应一个 JSON 文件。

## session_id 格式

由 IM 网关决定，不由 session_mgr 生成：
- `user:U123` — DM 或私聊，以 Slack/Telegram user ID 为 key
- `thread:T456` — 频道回复线程，以 thread_ts 或 message_id 为 key

HTTP API 路径目前以 `user_id`（数据库内部 UUID）为 session_id。

## 原子写入

```python
tmp = path.with_suffix(".json.tmp")
tmp.write_text(json.dumps(messages, ensure_ascii=False))
tmp.replace(path)          # 原子 rename
```

写入先落到 `.json.tmp`，完成后 rename 覆盖正式文件。rename 在同一文件系统内是原子操作——读取方永远看到完整文件，不会读到写到一半的状态。

## per-session asyncio.Lock

```python
_locks: dict[str, asyncio.Lock] = {}
```

同一 session_id 的并发请求通过 asyncio.Lock 串行化。两个请求同时到达时，第二个等第一个写完再读，避免历史丢失。

Lock 是懒创建的（第一次用到才建），字典无限增长——生产环境应用 LRU 或定期清理。

## 测试隔离

`monkeypatch.setattr(session_mgr, "SESSIONS_DIR", tmp_path / "sessions")` 即可隔离，无需其他处理。
