## 1. WAL + busy_timeout 接入

- [ ] 1.1 写失败测试（integration，真实 SQLite 文件）：经 `db.py` 打开连接后 `PRAGMA journal_mode` 返回 `wal`、`PRAGMA busy_timeout` 为配置的非零值
- [ ] 1.2 写失败测试：并发场景——一连接写、另一连接同时读同库不报 `database is locked`（WAL）；两连接近乎同时写，后者在 busy_timeout 内成功而非立即失败
- [ ] 1.3 实现：`db.py` 加统一内部连接入口 `_connect(path)`（connect → `PRAGMA journal_mode=WAL` + `PRAGMA busy_timeout=<ms>`），`execute` 与游标/迭代路径都改走它，跑绿 1.1/1.2

## 2. 回归与收尾

- [ ] 2.1 跑既有 integration（DB/store/runtime）确认 WAL/busy_timeout 不破坏现有行为；确认 `tmp_path` 测试隔离不受 `-wal`/`-shm` sidecar 影响
- [ ] 2.2 全仓确认无新增裸 `sqlite3.connect`（收敛到 `_connect` 入口）；运维文档注明备份/拷贝库需带 `-wal`/`-shm`
- [ ] 2.3 change 收尾：`make test-pr` 全绿 + `uv run pytest tests/integration -q` 对照 main 基线无新增失败 + `openspec validate sqlite-wal-concurrency --strict`
