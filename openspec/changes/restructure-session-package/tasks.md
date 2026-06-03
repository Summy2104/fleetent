> 纯结构重构：无新增行为，**用既有全量测试套件作为回归安全网**（每个结构步骤后跑全量，必须保持绿；"红" = 改坏了 import/行为，立即修）。

## 1. 基线

- [ ] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿；`mypy src` 现有错误数（作为"不新增"基准）

## 2. 移文件 + 建包

- [ ] 2.1 `git mv` `session_mgr.py`→`session/manager.py`、`session_index.py`→`session/index.py`
- [ ] 2.2 改包内 import（manager 引用 index 改 `from fleetent.session.index import ...`）；逐模块 import 自检通过
- [ ] 2.3 建 `session/__init__.py`：re-export 公共 API + 显式 `__all__`（load/load_meta/save/clear/reset/inject_message/list_session_ids/session_lock/start_session_maintenance/stop_session_maintenance/maybe_run_maintenance/cleanup_expired/enforce_capacity/SESSIONS_DIR 等，以 src+tests 实际使用为准）；`from fleetent.session import manager` 自检通过

## 3. 旧路径 shim

- [ ] 3.1 旧 `session_mgr.py`、`session_index.py` 改为 shim（re-export + `__all__`，**不含任何逻辑**）；`uv run python -c "from fleetent.session_mgr import save, SESSIONS_DIR"` 旧路径自检仍通过

## 4. 改 src 调用方到新公共 API

- [ ] 4.1 `server.py`、`cron_scheduler.py`、`tui/dispatch.py` 改 `from fleetent.session import manager as session_mgr`（函数体不动）；`uv run python -c "import fleetent.server, fleetent.cron_scheduler"` 导入成功

## 5. 测试 import + monkeypatch 目标随迁

- [ ] 5.1 `grep -rn "session_mgr" tests` 全量核对：**所有 monkeypatch `session_mgr` 模块属性（SESSIONS_DIR 等）的测试必须改 patch `fleetent.session.manager`**（shim 上 patch 不生效，漏改可能写真实 data/）；直接相关测试（test_session_mgr 等）import 改到新路径，其余纯 import 靠 shim
- [ ] 5.2 跑 session 相关测试子集绿；确认 `data/` 下无测试产生的新文件

## 6. 全量门禁 + 文档

- [ ] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿（与基线一致）
- [ ] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净；`mypy src` 不新增错误模式
- [ ] 6.3 更新 `docs/architecture.md`「当前模块地图」：session 从平铺改记为 `session/`
