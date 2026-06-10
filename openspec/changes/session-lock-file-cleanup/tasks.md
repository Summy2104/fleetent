## 1. TTL 清理连带删除 `.lock` 锚文件

- [ ] 1.1 Write failing tests for lock-file cleanup: 在 `tests/integration/test_session_mgr.py` 新增两个用例——①过期 session 主文件被 `cleanup_expired()` 删除后，其 `{session_id}.lock` 文件被连带删除；②未过期 session 的 `.lock` 文件保留不删（参照现有 `.todo` 连带删除用例的写法，`tmp_path` 隔离 SESSIONS_DIR）。运行最窄命令必须见红
- [ ] 1.2 Implement lock-file cleanup to pass tests: 在 `cleanup_expired()` 主文件删除成功的连带清理段补删 `{session_id}.lock`（`with suppress(OSError)`，与 `.resume` / `.todo` 处理一致）。同一最窄命令见绿

## 2. 收尾

- [ ] 2.1 运行 `uv run pytest tests/integration -q`（不带 `-x`）对照 main 基线确认无新增失败；`make test-pr` 全绿
