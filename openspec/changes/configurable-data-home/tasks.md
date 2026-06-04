## 1. 中心路径解析器 paths.py

- [x] 1.1 Write failing tests：`tests/unit/test_paths.py` —— 断言解析优先级：`FLEETENT_HOME` 设置时 `config_dir()`/`data_dir()` 指向 `$FLEETENT_HOME/{config,data}`；未设且检测到仓库标记时指向 `./config`/`./data`；未设且无仓库标记时回退 `~/.fleetent/{config,data}`；env 优先于仓库本地。用 `monkeypatch.setenv` + 临时 CWD/HOME 隔离
- [x] 1.2 Implement：创建 `src/fleetent/paths.py`，实现 `config_dir()`/`data_dir()` 与 base 优先级解析（`FLEETENT_HOME` → repo marker（`pyproject.toml` 含 `name="fleetent"` 或 `./config`）→ `~/.fleetent`），并导出派生便捷路径（settings/db/sessions 等）使测试转绿

## 2. 低 blast-radius 调用方迁移

- [x] 2.1 Write failing tests：扩展/新增单测断言 `eval_logger`、`tools/builtin_tools`（generated/uploads）、`integrations/sandbox/{config,enablement}` 的路径常量从 `paths.py` 派生；`monkeypatch.setenv("FLEETENT_HOME", tmp)` 时整体重定向，且既有 monkeypatch 模块常量方式仍生效
- [x] 2.2 Implement：将上述模块的硬编码 `data/`/`config/` 常量改为从 `paths.py` 派生使测试转绿

## 3. config.py 与 server.py 迁移

- [x] 3.1 Write failing tests：断言 `config.py` 的 `SETTINGS_YAML_PATH`/`MCP_SERVERS_YAML_PATH`/`logging.directory`/`diagnostics.export_dir`/`database_url` 默认值、`server.py` 的 `_MCP_YAML_PATH`/`_WEBHOOK_YAML_PATH` 从 `paths.py` 派生；仓库内默认行为不变（回归保护）
- [x] 3.2 Implement：迁移 `config.py`、`server.py` 路径来源使测试转绿

## 4. 数据库与会话路径迁移

- [x] 4.1 Write failing tests：断言 `user_store.DB_PATH`、`session/index.DB_PATH`、`session/manager.SESSIONS_DIR` 从 `paths.py` 派生；文件名维持现状（`fleetent.db`/`users.db`/`sessions`，不改名）；既有 session/user_store 测试的 monkeypatch 隔离仍通过
- [x] 4.2 Implement：迁移 `user_store.py`、`session/index.py`、`session/manager.py` 使测试转绿

## 5. 其余配置型路径与 agent/cron/model 迁移

- [x] 5.1 Write failing tests：断言 `agent_config.AGENTS_DIR`、`cron_scheduler.LEGACY_CRON_CONFIG_PATH`、`model/router.ROUTES_PATH`、`platform/admin_cli/*`（`init_config` 目录列表、`agents._SETTINGS_YAML`）从 `paths.py` 派生
- [x] 5.2 Implement：迁移上述模块使测试转绿

## 6. DATABASE_URL 旁路收编

- [ ] 6.1 Write failing tests：`observability/traces.py` 等不再出现硬编码 `sqlite:///data/...`；`DATABASE_URL` 设置时优先生效、未设时默认从 `data_dir()` 派生（锁定优先级与默认值语义不变）
- [ ] 6.2 Implement：将直接 `os.environ["DATABASE_URL"]` + 硬编码默认的读取点收编为经中心解析使测试转绿

## 7. 收尾

- [ ] 7.1 全仓库 grep 确认无残留绕过 `paths.py` 的硬编码 `Path("data/...")`/`Path("config/...")`（diagnostics 展示用字符串等非路径解析点除外，需在 PR 说明）
- [ ] 7.2 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -x -q` 通过；`uv run ruff format && uv run ruff check src tests`；`uv run mypy src` 不新增错误
- [ ] 7.3 更新 CLAUDE.md 数据目录/Gotchas 段：记录 `FLEETENT_HOME` 与解析优先级，标注路径常量已收口到 `paths.py`
