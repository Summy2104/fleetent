## Why

`session_mgr.py` 当前只有 `load()` / `save()` / `session_lock()`：session 消息历史以 JSON 文件写入 `data/sessions/{session_id}.json`，原子写 + per-session asyncio.Lock，但**没有任何过期与清理机制**。session 文件永久积累，磁盘随对话量持续增长（见 docs/capabilities/session.md「现状」第 67 行：「无自动清理，session 文件永久积累，磁盘持续增长」）。

这是 on-premises 部署的运维隐患：客户内网机器磁盘有限，长期运行后 `data/sessions/` 会无限膨胀。本 change 为 session 引入基于 TTL（最后活跃时间）的过期判定与一次性清理函数，TTL 时长经 `Settings` env 字段配置，落实 session.md 规划项「TTL 过期与自动清理」（第 75 行）与验收场景 4（第 107 行）。

## What Changes

- 在 `session_mgr.py` 新增**TTL 过期清理函数** `cleanup_expired(ttl_seconds=None) -> list[str]`：扫描 `SESSIONS_DIR`，删除最后活跃时间早于 `now - ttl` 的 session 文件，返回被删除的 session_id 列表。
- **TTL 以「最后活跃时间」计算，而非创建时间**——最后活跃时间取 session 文件的 `mtime`（`save()` 每次写入即刷新 mtime，无需新增存储）。
- TTL 时长**支持部署级配置**：在 `config.py` 的 `Settings` 增加 `session_ttl_days: int = 30`（env 可配，沿用 `context_*` / `permission_gate_*` 既有模式）；`session_mgr` 经惰性 `_default_config()` 读取（同 `context_mgr._default_config()`），调用参数 > Settings > 字段默认值三层优先级。
- 删除操作**幂等且容错**：单个文件删除失败（如并发已被删）不中断整批清理，记录日志后继续。
- 清理操作**记录在系统日志**（structlog），对齐 session.md 验收场景 4「清理操作记录在系统日志中」。
- 清理仅删除超期文件，**不触碰未超期 session、不触碰 `.json.tmp` 临时文件**（避免误删正在写入的原子写中间态）。
- 本 change**不实现后台触发调度**——`cleanup_expired()` 是无副作用调度的纯清理函数，触发方式（cron_scheduler 接入 vs 独立后台任务）作为 session.md 待决问题留待后续 change，本次只提供可被任意调度器调用的清理原语。

## Capabilities

### New Capabilities
- `session-ttl-cleanup`: 基于最后活跃时间（文件 mtime）的 session TTL 过期判定与一次性清理；TTL 时长经 `Settings` env 字段配置 + 调用参数覆盖；删除容错、跳过临时文件、记录系统日志、返回被删 session_id 列表。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。session_mgr 的 load/save/lock 行为不变；TTL 清理为纯新增能力。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/session_mgr.py`：新增 `cleanup_expired()` + `_default_config()`（惰性 `from fleetent.config import Settings`）+ `is_expired()` 纯判定辅助函数。
  - 修改 `config.py` 的 `Settings`：增加 `session_ttl_days: int = 30`（env 可配）。
- **配置**：解析优先级为**调用参数 > Settings（env）> pydantic 字段默认值**；测试通过传参或传 config 注入，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
- **测试**：新增 `tests/test_session_mgr.py` 中 TTL 清理用例（若文件已存在则补充用例）；monkeypatch `SESSIONS_DIR` 到 `tmp_path`，通过 `os.utime` 伪造文件 mtime 模拟超期。
- **不影响**：`load()` / `save()` / `session_lock()` 既有行为；原子写契约；不引入新依赖（仅用标准库 `os` / `pathlib` / `time`）。
