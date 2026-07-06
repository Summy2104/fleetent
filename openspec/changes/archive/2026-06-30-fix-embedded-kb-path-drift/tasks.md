## 1. 删除 legacy 迁移代码（clean-break，TDD）

- [x] 1.1 测试先行：把 `tests/integration/test_tenant_router.py` 中断言 legacy-flat 自动迁移的用例（:169 起）**改写**为 clean-break 断言——预置 `tenants/<t>/kb.db`（租户根）与/或 `tenants/<t>/kb/kb.db`（kb/ 根）+ sidecar 后调 `tenant_scope`/`ensure_tenant_kb_dir`，断言：`kb/data/` 被幂等建立、**旧址文件保持原地未被搬迁**。`uv run pytest <file>::<test> -x -q` 见红
- [x] 1.2 实现：`tenant_router.ensure_tenant_kb_dir` 移除 legacy 迁移分支（`Path.replace` 搬迁），简化为"幂等 `mkdir(parents=True)` 建 `kb/data/` 并返回"。见绿
- [x] 1.3 确认 `_KB_FILENAMES` / `_SQLITE_SIDECAR_SUFFIXES` 若仅服务于已删迁移则一并清理（否则保留）；无其它 import 残留

## 2. spec 漂移修正

- [x] 2.1 `tenant-scoped-db-routing` spec delta（本 change specs/）：两条 requirement 内 `<tenant>/kb/kb.db` / `kb/kb_vectors.db` 全部更正为 `kb/data/...`；"KB 文件分组"requirement 增 clean-break 声明 + "legacy 旧址不自动迁移"场景
- [x] 2.2 grep 确认 specs 内无残留 `kb/kb.db`（非 `kb/data/`）：`grep -rnE "kb/kb\.db|/kb/kb_vectors" openspec/specs` 仅 archive 历史可留

## 3. 收尾门禁

- [x] 3.1 `openspec validate fix-embedded-kb-path-drift --strict`
- [x] 3.2 `make test-pr` + `make test-integration-ci` 全绿（含 `test_tenant_router`）
- [x] 3.3 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [x] 3.4 功能分支 `openspec archive fix-embedded-kb-path-drift`（同步 tenant-scoped-db-routing spec）
- [x] 3.5 所有 tasks.md checkbox 标 `[x]`
