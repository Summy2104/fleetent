> 纯结构重构：无新增行为，**用既有全量测试套件作为回归安全网**（每个结构步骤后跑全量，必须保持绿；"红" = 改坏了 import/行为，立即修）。

## 1. 基线

- [x] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`（基线 1 failed[test_agent_loop.py::test_run_sync_passes_effective_sandbox_mode 预存]/2595 passed/16 skipped）；`mypy src` 32 errors in 16 files（作为"不新增"基准）

## 2. 移文件 + 建包

- [x] 2.1 `git mv` `session_mgr.py`→`session/manager.py`、`session_index.py`→`session/index.py`
- [x] 2.2 改包内 import（manager 引用 index 改 `from fleetent.session import index as session_index`）；逐模块 import 自检通过
- [x] 2.3 建 `session/__init__.py`：re-export 公共 API + 显式 `__all__`（load/load_meta/save/clear/reset/inject_message/list_session_ids/session_lock/start_session_maintenance/stop_session_maintenance/maybe_run_maintenance/cleanup_expired/enforce_capacity/is_expired/is_over_capacity/SESSIONS_DIR）；`from fleetent.session import manager` 自检通过

## 3. 旧路径 shim

- [x] 3.1 旧 `session_mgr.py`、`session_index.py` 改为 shim（`from fleetent.session.manager import *` / `...index import *`，**不含任何逻辑**，与 sandbox shim 范式一致）；`from fleetent.session_mgr import save, SESSIONS_DIR` 旧路径自检仍通过

## 4. 改 src 调用方到新公共 API

- [x] 4.1 `server.py`、`cron_scheduler.py`、`tui/dispatch.py`、`im_gateway/normalizer.py` 改 `from fleetent.session import manager as session_mgr`（函数体不动）；`import fleetent.server, fleetent.cron_scheduler` 导入成功

## 5. 测试 import + monkeypatch 目标随迁

- [x] 5.1 `grep -rn "session_mgr" tests` 全量核对：所有 monkeypatch session 模块属性的测试改 patch `fleetent.session.manager` / `fleetent.session.index`（test_session_mgr / test_session_index / test_session_admin_store / test_integration / test_normalizer / test_im_gateway / test_eval_logger / test_context_mgr / test_scheduled_task_session_binding）；test_tui_dispatch 经 `d.session_mgr` 间接指向 manager 无需改。tests 中已无任何旧 shim 路径引用
- [x] 5.2 全量套件绿（与基线一致）；session 相关 monkeypatch 已隔离到 tmp_path，本 change 触及的测试不向 `data/` 写新文件（既存的 test_cron_scheduler.py::test_fire_* 未 patch SESSIONS_DIR 的 data/ 泄漏为 change 范围外的预存问题，迁移前后一致）

## 6. 全量门禁 + 文档

- [x] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`：1 failed[同基线 test_run_sync_passes_effective_sandbox_mode 预存]/2595 passed/16 skipped——与基线完全一致，无新增失败
- [x] 6.2 `ruff format` 本 change 文件（无改动）+ `ruff check` 改动文件干净；`mypy src` 32 errors in 16 files（与基线一致，2 个 session Settings call-arg 仅从 session_mgr.py 迁到 session/manager.py，无新增错误模式）
- [x] 6.3 更新 `docs/architecture.md`「当前模块地图」：session 从平铺 `session_mgr.py` 改记为 `session/` 包（manager/index）
