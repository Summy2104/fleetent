## 1. CLI namespace 调度（TDD）

- [ ] 1.1 Write failing tests：`tests/unit/test_main_subcommands.py`
  - `fleetent platform validate-config --format json` dispatches to Platform CLI with `prog="fleetent platform"`
  - `fleetent admin ...` no longer dispatches and exits as an unknown top-level command
  - `fleetent agent run` still does not import Platform CLI
- [ ] 1.2 Implement：`src/fleetent/__main__.py` 将 `admin` 分支改为 `platform` 分支，懒加载 Platform CLI
- [ ] 1.3 Verify green：运行 `uv run pytest tests/unit/test_main_subcommands.py -x -q`

## 2. CLI 包迁移（TDD）

- [ ] 2.1 Write failing tests：更新 admin CLI integration/unit 测试导入路径为
  `fleetent.platform.platform_cli.main`，并将 helper 命名从 `run_admin` 改为 `run_platform`
- [ ] 2.2 Implement：将 `src/fleetent/platform/admin_cli/` 迁移为
  `src/fleetent/platform/platform_cli/`；更新内部 import、测试、文档引用；不保留 `admin_cli` shim
- [ ] 2.3 Verify green：运行 CLI 相关测试
  `uv run pytest tests/integration/test_admin.py tests/unit/test_admin_init_config.py tests/integration/test_pilot_readiness_admin.py -x -q`

## 3. `fleetent platform serve`（TDD）

- [ ] 3.1 Write failing tests：Platform CLI 支持 `serve`，解析 `--host`、`--port`、`--reload`，
  并调用 uvicorn runner 启动 `fleetent.server:app`；测试 monkeypatch runner，不真起服务
- [ ] 3.2 Implement：新增 serve 子命令，默认 host/port 与现有开发入口保持兼容；Makefile
  `platform` target 改用 `uv run fleetent platform serve --host 127.0.0.1 --port $(PLATFORM_PORT)`
- [ ] 3.3 Verify green：运行 serve CLI 测试与 `make -n platform`

## 4. `fleetent platform upgrade`（TDD）

- [ ] 4.1 Write failing tests：`fleetent platform upgrade --dry-run` 委托现有 upgrade 逻辑；
  参数 `--database-url`、`--backup-dir`、`--backup-only` 透传且 stdout/stderr/exit code 保持一致
- [ ] 4.2 Implement：新增 upgrade 子命令，复用 `scripts/upgrade.py` 现有 main/函数语义；
  Docker entrypoint 和运维文档主路径改为 `fleetent platform upgrade`
- [ ] 4.3 Verify green：运行 upgrade 脚本相关测试与新增 CLI 测试

## 5. Makefile / install scripts / docs 迁移

- [ ] 5.1 Write failing tests or static checks：更新现有文档/安装测试断言，不再出现用户入口
  `fleetent admin`、裸 `uvicorn fleetent.server:app` 作为主启动命令、裸 `scripts/upgrade.py`
  作为主升级命令
- [ ] 5.2 Implement：更新 Makefile、README、install scripts、Docker entrypoint、operations docs、
  OpenSpec specs 中的 CLI 文案
- [ ] 5.3 Verify green：运行受影响文档/安装/entrypoint 测试

## 6. 边界与收尾验证

- [x] 6.1 Verify：`rg "fleetent admin|platform\\.admin_cli|admin_cli|uvicorn fleetent\\.server:app|python -m uvicorn fleetent\\.server:app" src tests Makefile README.md docs scripts openspec/specs`，确认仅历史 archive 或明确非主入口处残留
- [x] 6.2 Verify：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`
- [x] 6.3 Verify：`make test-pr`
- [x] 6.4 Verify：`uv run pytest tests/integration -q`，对照 main 基线无新增失败
