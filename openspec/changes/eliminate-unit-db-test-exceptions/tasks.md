## 0. 前置确认

- [ ] 0.1 确认 `clarify-test-layer-boundaries` 已落地或本分支已包含其 guard 基础
- [ ] 0.2 记录 `tests/unit/` 中 remaining DB-backed baseline，至少覆盖：
  `test_im_user_store.py`、`test_im_connector_store.py`、`test_im_connector_config.py`、
  `test_im_connector_manager.py`、`test_im_channel_allowlist.py`、`test_layered_budget.py`,
  `test_session_index.py`、`test_sub_agent.py`、`test_sub_agent_lifecycle.py`、
  `test_context_mgr.py`、`test_agent_loop.py`
- [ ] 0.3 标记只读 shim / API / path assertion 文件，避免误迁移：
  `test_im_identity_submodule.py`、`test_im_connector_store_submodule.py`,
  `test_im_channel_allowlist_submodule.py`、`test_im_module_public_api.py`,
  `test_db_session_paths.py`
- [ ] 0.4 确认迁移策略：纯 DB persistence 文件整文件迁移；混合文件只拆分 DB-backed tests；只读 shim /
  API / path assertion 留在 unit

## 1. Guard 收紧：unit 禁止真实 DB 依赖

- [ ] 1.1 Write failing tests: 扩展 `tests/unit/test_test_layer_guard.py`，构造临时 unit files，断言 guard
  能检出 `import sqlite3`、`sqlite3.connect`、`monkeypatch.setattr(..., "DB_PATH", ...)`、
  `_init_db()`、`DATABASE_URL` 设置为 `sqlite:///...`、`create_database("sqlite:///...")`
- [ ] 1.2 Write failing tests: 断言 guard 允许纯 `tmp_path` 文件解析 / 配置路径测试，以及只读 legacy
  shim / public API / path constant 兼容断言
- [ ] 1.3 Write failing tests: 断言 guard 不允许用 `tmp_path` 创建真实 DB-backed store 测试，且不允许通过
  allowlist 放行真实 SQLite / DB-backed 行为
- [ ] 1.4 Implement: 收紧 `scripts/check_test_layers.py` 规则，使 guard 基于 DB 行为命中 unit 测试；仅允许
  明确的非 DB 误报例外，使 1.1 / 1.2 / 1.3 转绿
- [ ] 1.5 Verify green: 运行 `uv run pytest tests/unit/test_test_layer_guard.py -x -q`

## 2. 迁移 legacy DB-backed unit tests

- [ ] 2.1 Write failing tests: 运行 `uv run python scripts/check_test_layers.py`，确认当前 unit 目录因
  remaining DB-backed tests 失败（红）
- [ ] 2.2 Implement: 将纯 store persistence 文件迁移到 `tests/integration/`，包括 IM user / connector /
  allowlist store、session index、layered budget store、sub-agent DB lifecycle 等真实 SQLite 行为测试
- [ ] 2.3 Implement: 对混合文件做有限拆分：纯 enum / validation / import / config 逻辑留在
  `tests/unit/`，DB-backed tests 移到 `tests/integration/`
- [ ] 2.4 Implement: 处理同名 integration 文件冲突，采用合并或 `_db` / `_store` 后缀重命名；更新
  imports，避免 pytest module import mismatch
- [ ] 2.5 Verify green: 运行 `uv run python scripts/check_test_layers.py`，确认 unit 层真实 DB 依赖清零

## 3. 分层语义验证

- [ ] 3.1 Verify green: 运行 `uv run pytest tests/unit -x -q`，确认 unit 层仍通过且不依赖真实 DB
- [ ] 3.2 Verify green: 运行 `uv run pytest tests/integration -x -q`，确认迁移后的 DB-backed tests 通过
- [ ] 3.3 Verify green: 运行 `uv run pytest -x -q`，确认完整测试仍通过

## 4. 文档和命令契约

- [ ] 4.1 Write failing tests: 更新或新增文档 contract test，断言项目指南明确 `sqlite3` / `DB_PATH` /
  `_init_db()` / `DATABASE_URL=sqlite:///...` 属于 integration，不得放在 unit
- [ ] 4.2 Implement: 更新 `AGENTS.md` / `CLAUDE.md`，删除或改写“legacy store 迁移前可 monkeypatch
  `DB_PATH`”表述；说明 `tmp_path` 只有用于纯文件边界时可留 unit，真实 DB file、schema、CRUD 或
  store runtime 协作均归 integration
- [ ] 4.3 Implement: 更新 Makefile / docs 中 test-layer guard 说明，标注 guard 已覆盖 unit 层 DB-backed
  行为，并保留只读 shim / API / path assertion 的 unit 归属
- [ ] 4.4 Verify green: 运行相关文档 contract test

## 5. 收尾

- [ ] 5.1 运行 `uv run ruff format src tests scripts`
- [ ] 5.2 运行 `uv run ruff check src tests scripts`
- [ ] 5.3 运行 `uv run mypy src`
- [ ] 5.4 运行 `uv run pytest -x -q`
- [ ] 5.5 运行 `uv run python scripts/check_test_layers.py`
- [ ] 5.6 运行 `openspec validate eliminate-unit-db-test-exceptions --strict`
- [ ] 5.7 运行 `git diff --check`
