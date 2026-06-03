## Context

蓝图已确立目标结构与迁移约定；sandbox 迁移（PR #98）已立范式。现状：`session_mgr.py`（含维护循环、TTL/LRU、锁、读写 API）+ `session_index.py`（SQLite 元数据索引，仅被 manager 引用）平铺。

src 直接调用方（已扫描）：
- `server.py`：`from fleetent import session_mgr, user_store`（module-style）
- `cron_scheduler.py`：lazy `from fleetent import session_mgr`
- `tui/dispatch.py`：`from fleetent import session_mgr`
- `session_index` 只被 `session_mgr` 引用（包内化）

tests（已扫描）：`test_session_mgr`、`test_session_admin_store`、`test_scheduled_task_session_binding`、`test_context_mgr`、`test_eval_logger`、`test_integration`、`test_im_gateway` 等触及 `session_mgr.` / `SESSIONS_DIR`。

## Goals / Non-Goals

**Goals**：2 文件迁入 `session/`、去前缀、`__init__` 收口、src 调用方改新路径、旧路径 shim、monkeypatch 目标修正、全量门禁绿、行为不变。
**Non-Goals**：不改 session 持久化格式 / 原子写 / 锁语义 / 维护循环逻辑；不动 `schedule_store` 等邻域。

## Decisions

### D1 — 文件映射（去前缀）
```
session_mgr.py   → session/manager.py
session_index.py → session/index.py
```
`git mv` 保留历史。

### D2 — 公共 API 收口 `session/__init__.py`
manager 的对外函数面较宽（module-style 调用）：`load, load_meta, save, clear, reset, inject_message, list_session_ids, session_lock, start_session_maintenance, stop_session_maintenance, maybe_run_maintenance, cleanup_expired, enforce_capacity, is_expired, is_over_capacity, SESSIONS_DIR` 等以 src+tests 实际使用为准，`__all__` 显式列出。index 的 `record_activity, get, list_by_user, count, total_message_count` 视外部使用决定是否从包级导出（若仅 manager 用则不导）。

### D3 — module-style 调用方的改法
`server.py` / `cron_scheduler.py` / `tui/dispatch.py` 用 `session_mgr.xxx()` 形式调用。改成 `from fleetent.session import manager as session_mgr`，函数体零改动、diff 最小。

### D4 — 旧路径 shim
`session_mgr.py` / `session_index.py` 改为 re-export shim（`from fleetent.session.manager import *` + 显式名 + `__all__`），不承载逻辑。

### D5 — monkeypatch 目标必须随迁（本包特有风险）
`from ... import *` 把 `SESSIONS_DIR` **复制**进 shim 命名空间；测试若仍 patch `fleetent.session_mgr.SESSIONS_DIR`，改的是 shim 的副本，`manager` 内部读自己的全局——patch 失效，测试可能写真实 `data/`。因此本 change **必须**把所有 monkeypatch `session_mgr` 模块属性的测试改为 patch `fleetent.session.manager`；纯 import 测试可留 shim。`grep -rn "session_mgr" tests` 逐个核对 patch 类用法。

## Risks / Trade-offs

| 风险 | 缓解 |
|------|------|
| monkeypatch 目标漂移致测试写真实 data/ | D5 强制随迁所有 patch 目标；全量测试 + 检查 data/ 无新文件 |
| `session_mgr` 内 lazy import `tools`（释放 sandbox） | 保持 lazy import 原样，只改模块路径 |
| `_get_lock` 等私有符号被测试触达 | 测试改从 `fleetent.session.manager` 直接 import 私有名 |
| import 改漏 | shim 兜底 + 全量 pytest + 关键符号自检 |

## 验收

- `session/` 成包，`__init__.py` 收口公共 API，`__all__` 显式。
- 旧 `session_mgr.py` / `session_index.py` 仅 re-export（无逻辑）。
- `server` / `cron_scheduler` / `tui/dispatch` 从 `fleetent.session` 导入。
- 无任何测试 monkeypatch 旧 shim 路径的模块属性。
- 全量 `ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q` 绿；`ruff check` 干净；`mypy src` 不新增错误模式。
- 自检：`from fleetent.session import manager` 且 `manager.SESSIONS_DIR` 存在；旧路径 `from fleetent.session_mgr import save` 仍可用。
