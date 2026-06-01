## 0. 前置确认

- [x] 0.1 确认默认 DB 文件名从 `data/users.db` 改为 `data/fleetent.db`
- [x] 0.2 确认不做旧 `data/users.db` 自动迁移、fallback 或兼容读取
- [x] 0.3 确认本 change 不做 backup / upgrade 脚本

## 1. Runtime defaults

- [x] 1.1 Write failing tests: `Settings().database_url` 默认等于 `sqlite:///data/fleetent.db`
- [x] 1.2 Write failing tests: `create_database("sqlite:///data/fleetent.db")` path 为 `data/fleetent.db`
- [x] 1.3 Write failing tests: observability trace fallback 使用 `sqlite:///data/fleetent.db`
- [x] 1.4 Implement: 更新 config、DB runtime 测试相关默认值和 observability fallback
- [x] 1.5 Verify green: 运行 `uv run pytest tests/unit/test_config.py tests/integration/test_db.py tests/integration/test_trace_events.py -x -q`

## 2. Legacy DB_PATH default

- [x] 2.1 Write failing tests: `user_store.DB_PATH` 默认等于 `Path("data/fleetent.db")`
- [x] 2.2 Write failing tests: legacy re-export modules inherit the new default DB_PATH
- [x] 2.3 Implement: 更新 legacy `user_store.DB_PATH` default
- [x] 2.4 Verify green: 运行 `uv run pytest tests/integration/test_user_store.py tests/integration/test_api_key_store.py -x -q`

## 3. Config and migration defaults

- [x] 3.1 Write failing tests or static checks: `config/settings.yaml.example` 使用 `sqlite:///data/fleetent.db`
- [x] 3.2 Write failing tests or static checks: `alembic.ini` 默认 URL 使用 `sqlite:///data/fleetent.db`
- [x] 3.3 Implement: 更新示例配置和 Alembic 默认 URL
- [x] 3.4 Verify green: 运行相关配置测试或静态检查

## 4. Docs and specs

- [x] 4.1 更新 `openspec/specs/database-runtime/spec.md`
- [x] 4.2 更新 `openspec/specs/configuration/spec.md`
- [x] 4.3 更新 `docs/capabilities/deployment.md`
- [x] 4.4 更新其他当前能力文档中仍描述产品默认路径为 `data/users.db` 的引用
- [x] 4.5 文档明确：已有本地 `data/users.db` 不自动迁移，需要手动重命名或重新初始化

## 5. Final verification

- [x] 5.1 运行 `uv run ruff format src tests`
- [x] 5.2 运行 `uv run ruff check src tests`
- [x] 5.3 运行 `uv run mypy src`
- [x] 5.4 运行 `uv run pytest -x -q`
- [x] 5.5 运行 `openspec validate database-default-path-rename --strict`
- [x] 5.6 运行 `git diff --check`
