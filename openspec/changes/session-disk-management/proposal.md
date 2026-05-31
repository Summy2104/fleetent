## Why

`session_mgr.py` 当前对 session 文件**没有任何容量上限**：单个 session 文件可无限增长，整个 `data/sessions/` 目录的 session 数量与总大小也无上限（docs/capabilities/session.md 第 71 行：「单个 session 文件可无限增长……但不限制文件大小」；第 88 行规划「总 session 文件大小上限或最大保留数量」）。

TTL 清理（`session-ttl-cleanup`）只能淘汰「久未活跃」的 session，但在高并发短周期场景下，大量近期 session 可能在 TTL 到期前就已撑爆磁盘。on-premises 部署磁盘有限，需要一个**基于总量/数量上限的兜底淘汰**：当 session 总大小或总数超限时，按 LRU（最久未活跃优先）淘汰最旧的 session，直到回落到阈值以内。本 change 落实 session.md 规划项「磁盘空间管理」（第 88 行）。

## What Changes

- 在 `session_mgr.py` 新增 **LRU 容量淘汰函数** `enforce_capacity(max_total_bytes=None, max_count=None) -> list[str]`：当 session 总大小超过 `max_total_bytes`、或 session 总数超过 `max_count` 时，按最后活跃时间（文件 mtime）升序（最旧优先）删除 session 文件，直到两个上限均满足，返回被删除的 session_id 列表。
- LRU 口径以**最后活跃时间（文件 mtime）**排序——与 `session-ttl-cleanup` 同一时间口径，复用 `save()` 写入即刷新 mtime 的特性，无需新增存储。
- 上限**支持部署级配置**：在 `config.py` 的 `Settings` 增加 `session_max_total_mb: int = 1024`、`session_max_count: int = 10000`（env 可配，沿用 `context_*` / `permission_gate_*` 既有模式）；`session_mgr` 经惰性 `_default_config()` 读取（同 `context_mgr._default_config()`），调用参数 > Settings > 字段默认值三层优先级。
- 上限语义为**可独立关闭**：阈值配置为 `0` 或 None 时表示该维度不限制（仅按另一维度淘汰，或全不淘汰）。
- 删除**幂等且容错**：单个文件删除失败不中断整批，记录日志后继续；跳过 `.json.tmp` 临时文件。
- 淘汰操作**记录在系统日志**（structlog），含触发原因（超大小 / 超数量）与被淘汰数量。
- 本 change**不实现后台触发调度**——`enforce_capacity()` 是无副作用调度的纯淘汰函数，触发方式留待后续 change（与 TTL 清理的触发归属同属 session.md 待决问题）。

## Capabilities

### New Capabilities
- `session-disk-management`: 基于总大小上限与最大数量上限的 session LRU 容量淘汰；按最后活跃时间（文件 mtime）最旧优先删除直至回落阈值；上限经 `Settings` env 字段配置 + 调用参数覆盖、可按维度关闭；删除容错、跳过临时文件、记录系统日志、返回被删 session_id 列表。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。session_mgr 的 load/save/lock 行为不变；LRU 容量淘汰为纯新增能力。 -->

## Impact

- **代码**：
  - 修改 `src/fleetent/session_mgr.py`：新增 `enforce_capacity()` + 复用/扩展 `_default_config()`（惰性 `from fleetent.config import Settings`）+ 扫描辅助（收集文件大小与 mtime）。
  - 修改 `config.py` 的 `Settings`：增加 `session_max_total_mb: int = 1024`、`session_max_count: int = 10000`（env 可配）。
- **配置**：解析优先级为**调用参数 > Settings（env）> pydantic 字段默认值**；测试通过传参或传 config 注入，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
- **测试**：新增 `tests/test_session_mgr.py` 中 LRU 容量用例（与 TTL 用例共文件）；monkeypatch `SESSIONS_DIR → tmp_path`，通过文件大小与 `os.utime` 伪造 mtime 构造超限场景。
- **不影响**：`load()` / `save()` / `session_lock()` 既有行为；原子写契约；不引入新依赖（仅用标准库 `os` / `pathlib`）。
