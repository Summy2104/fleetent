> 纯结构重构，蓝图收官包。**前置：session/skills/model/tools 四包已迁**。最大机械面是 39 处 agent_loop patch 随迁，分批推进。

## 1. 基线

- [x] 1.1 记录基线：`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 全绿；`mypy src` 现有错误数；`get_schemas()` 工具数

## 2. 移文件 + 建包

- [x] 2.1 `git mv` 13 文件入 `runtime/`：`agent_loop.py`→`loop.py`、`context_mgr.py`→`context.py`、`agent_runtime.py`→`snapshot.py`、其余 10 个同名移动
- [x] 2.2 改包内 import（loop 对 12 兄弟模块改子模块直引；loop↔sub_agent lazy 边界原样保留仅改路径）；逐模块 import 自检；**`import fleetent.runtime.loop` 后 `get_schemas()` 非空**
- [x] 2.3 建 `runtime/__init__.py`：re-export 公共 API + 显式 `__all__`（run/run_stream/CancelToken/CancellationChecker/load_active/SubAgentExecutor 等，以实际外部使用为准）；`from fleetent.runtime import run, run_stream, CancelToken` 自检通过

## 3. 旧路径 shim（13 个）

- [x] 3.1 13 个旧路径全改 shim（re-export + `__all__`，不含逻辑；`agent_loop.py`/`context_mgr.py`/`agent_runtime.py` 注释标注新名 loop/context/snapshot）；`uv run python -c "from fleetent.agent_loop import run; from fleetent.cancellation import CancelToken"` 旧路径自检通过

## 4. 改 src 调用方到新公共 API

- [x] 4.1 `cron_scheduler.py`、`__main__.py`、`server.py`、`tui/dispatch.py`、`im_gateway/normalizer.py`、`tools/builtin_tools.py` 改 `from fleetent.runtime import ...`（module-style 用 `from fleetent.runtime import loop as agent_loop`）；`uv run python -c "import fleetent.server, fleetent.cron_scheduler, fleetent.__main__"` 导入成功

## 5. 测试 patch 目标随迁（分批，本包重头）

- [x] 5.1 `grep -rn "fleetent\.agent_loop\|setattr(agent_loop" tests` 列全 39 处（18 文件），按文件分批：patch 前缀 `fleetent.agent_loop` → `fleetent.runtime.loop`（符号名不变），每批改完即跑该文件测试
- [x] 5.2 `context_mgr` 私有名测试（`_keep_tail`/`AntiFlapState` 等）import 改 `fleetent.runtime.context`；其余治理模块测试 import 改新路径或留 shim
- [x] 5.3 收尾核对：`grep -rn "patch(\"fleetent\.agent_loop\|setattr(agent_loop\|patch(\"fleetent\.context_mgr" tests` 零残留

## 6. 全量门禁 + 文档

- [x] 6.1 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿（与基线一致）；`get_schemas()` 工具数与基线一致
- [x] 6.2 `uv run ruff format` 本 change 文件 + `ruff check src tests` 干净；`mypy src` 不新增错误模式
- [x] 6.3 更新 `docs/architecture.md`：runtime 域改记为 `runtime/`，标注蓝图 7 包全部落地；更新 CLAUDE.md 模块地图中 agent_loop/context_mgr 等路径表述
- [x] 6.4 在蓝图 follow-up 记录：可启动「统一删 shim」收尾 change（前提：全库调用方已切新路径）
