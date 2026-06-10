## 1. 向量后端 WAL + busy_timeout

- [x] 1.1 写失败测试（integration，真实向量库文件）：`SQLiteVectorBackend` 连接后 `journal_mode`=wal、`busy_timeout` 非零；并发——一连接写、另一读不报 locked；两写后者 busy_timeout 内成功
- [x] 1.2 实现：`vector_store/backend.py` 加统一连接入口（aiosqlite.connect → PRAGMA journal_mode=WAL + busy_timeout，复用 db.py 同值），upsert/search/delete 都改走它，跑绿 1.1

## 2. 回归与收尾

- [ ] 2.1 跑既有 vector_store 单测/集成确认行为不变；`tmp_path` 隔离不受 sidecar 影响
- [ ] 2.2 `make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate vector-backend-wal-concurrency --strict`
