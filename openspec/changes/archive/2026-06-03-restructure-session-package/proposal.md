## Why

落实蓝图 `runtime-package-blueprint`（spec `package-architecture`）的**第二个逐包迁移**（序列：sandbox✅ → **session** → skills → model → tools → runtime）：把平铺的 `session_mgr.py`、`session_index.py` 收进 `session/` 能力包。session 域自包含（index 只被 manager 引用）、调用方少，是 sandbox 之后 blast radius 最小的一包。

## What Changes

- **迁移 2 文件**到 `src/fleetent/session/`，去冗余前缀（`git mv` 保留 blame）：
  `session_mgr.py`→`manager.py`、`session_index.py`→`index.py`。
- **建 `session/__init__.py`** re-export 公共 API（以 src+tests 实际使用为准收口）。
- **改包内 import**（manager → index）。
- **旧扁平路径留 re-export shim**（`session_mgr.py`、`session_index.py`，不承载逻辑）。
- **改 src 直接调用方**到新公共 API：`server.py`、`cron_scheduler.py`、`tui/dispatch.py`（module-style 用法改 `from fleetent.session import manager as session_mgr` 保持函数体不动）。
- **迁移直接相关测试的 import 与 monkeypatch 目标**（`SESSIONS_DIR` 等 patch 必须指向新模块，shim 上的 patch 不生效——这是本包特有风险）。
- 行为不变、无 schema 变更。

## Capabilities

### Modified Capabilities
- `package-architecture`: 记录 session 域**已完成包化**——`session/` 成包、公共 API 收口、旧路径仅 shim、契约/行为不变。

## Impact

- **代码**：新增 `src/fleetent/session/`（2 模块 + `__init__.py`）；旧 2 文件变 shim；`server`/`cron_scheduler`/`tui/dispatch` 改 import。
- **测试**：monkeypatch `session_mgr.SESSIONS_DIR` 的测试**必须**改 patch 目标到 `fleetent.session.manager`（shim 兜底对 monkeypatch 无效，漏改会触碰真实 `data/`）；纯 import 的测试可靠 shim 渐进迁移。
- **不受影响**：session JSON 持久化格式、原子写（`.json.tmp → rename`）、per-session asyncio.Lock、TTL/LRU 清理逻辑。
- **依赖**：蓝图（已归档）+ sandbox 迁移范式（已落地）。
- **后续**：skills → model → tools → runtime。
- **分支**：基于并 PR 合回 `main`。
