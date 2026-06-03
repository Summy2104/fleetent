## Context

`session_mgr.py`（共 43 行）持久化 session 消息历史 JSON，无任何容量上限。docs/capabilities/session.md 第 71 行：「单个 session 文件可无限增长（context_mgr 压缩缓解 token 问题，但不限制文件大小）」；第 88 行规划「磁盘空间管理：总 session 文件大小上限或最大保留数量，超限时按 LRU 清理最旧的 session」。

`session-ttl-cleanup`（同波次）按最后活跃时间淘汰久未活跃 session，但 TTL 是「时间维度」兜底；本 change 提供「容量维度」兜底——即便所有 session 都在 TTL 内，只要总量/数量超限就按 LRU 淘汰最旧者。两者时间口径一致（均用文件 mtime），互补不重叠。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（阈值/路径必须可 monkeypatch 注入）；新模块结构 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 monkeypatch `session_mgr.SESSIONS_DIR → tmp_path`，绝不触碰 `data/`。

## Goals / Non-Goals

**Goals:**
- 提供 `enforce_capacity(max_total_bytes=None, max_count=None) -> list[str]`：超限时按 LRU（最旧优先）淘汰至回落阈值，返回被删 session_id 列表。
- LRU 排序口径为最后活跃时间（文件 mtime），与 TTL 清理一致。
- 上限经 `Settings.session_max_total_mb` / `session_max_count` env 字段配置 + 调用参数覆盖。
- 阈值可按维度关闭（0 / None 表示该维度不限制）。
- 删除容错、跳过 `.json.tmp`、记录系统日志（含触发原因）。

**Non-Goals:**
- 不实现后台触发调度（与 TTL 清理触发归属同属 session.md 待决问题，留待后续 change）。
- 不实现单个 session 文件内部的截断/压缩（那是 context_mgr 的 token 压缩职责）。
- 不依赖 `session-metadata-index`（本 change 用文件系统 stat 自洽；后续可选改用索引加速，但不在本范围）。
- 不改动 `load()` / `save()` / `session_lock()` 与原子写契约。

## Decisions

### D1：LRU 口径用文件 mtime，与 TTL 清理一致
淘汰顺序按文件 mtime 升序（最久未活跃在前）。`save()`（行 37-42）原子写刷新目标文件 mtime，故 mtime 即「最后活跃时间」。
**为何**：与 `session-ttl-cleanup` D1 同一口径，零新增存储，两个清理能力语义统一、便于理解与组合。
**Alternatives**：①按文件大小排序（先删最大）——被否，与「LRU」语义不符，session.md 第 88 行明确「清理最旧的 session」；②依赖 `session-metadata-index` 的 `updated_at`——被否，会引入对另一 change 的硬依赖，本 change 应自洽（文件 stat 已足够）。

### D2：两维度上限独立判定，淘汰至双双满足
扫描收集每个 session 文件的 `(session_id, size, mtime)`。计算 `total_bytes` 与 `count`：
- 若 `max_total_bytes` 有效（>0）且 `total_bytes` 超限，或 `max_count` 有效（>0）且 `count` 超限 → 触发淘汰。
- 按 mtime 升序逐个删除，每删一个从累计中扣除其 size 与计数，直到两个有效上限**均满足**为止。

**为何**：两维度是「或」触发、「且」停止——任一超限即清理，清到两者都不超才停，保证退出后两个约束都成立。
**Alternatives**：只支持单一维度——被否，session.md 第 88 行明确「总大小上限**或**最大保留数量」二者皆需。

### D3：阈值经 Settings 配置 + 调用参数覆盖（对齐 context_mgr 模式）
- `config.py` 的 `Settings` 增加 `session_max_total_mb: int = 1024`、`session_max_count: int = 10000`（env 可配，与 `context_max_tokens` 同类）。
- `session_mgr._default_config()`（若 `session-ttl-cleanup` 已建则扩展之）返回 `max_total_bytes = session_max_total_mb * 1024 * 1024`、`max_count = session_max_count`。
- `enforce_capacity(max_total_bytes=None, max_count=None)`：None 时回落 `_default_config()`。

解析优先级：**调用参数 > Settings（env）> pydantic 字段默认值**。测试通过传参或 monkeypatch `_default_config`，不实例化真 `Settings`。
**为何**：项目运行旋钮统一走 Settings env 字段；Settings 字段默认值即单一事实来源。
**Alternatives**：模块级常量 / settings.yaml——同 `session-ttl-cleanup` D2 理由被否。

### D4：维度关闭语义
阈值为 `0`（或 None 回落后仍判定为 0）表示该维度**不限制**：跳过该维度的超限判定、不据其触发淘汰、也不作为停止条件。两维度都关闭时 `enforce_capacity` 直接返回空列表（无淘汰）。
**为何**：on-premises 部署诉求各异，有的只关心数量、有的只关心总大小；可独立关闭比强制双约束灵活。
**Alternatives**：不支持关闭、强制双约束——被否，灵活性不足，且默认值过大时形同未启用反而需要显式关闭手段。

### D5：删除容错、跳过临时文件、纯淘汰原语
逐个 `unlink`，单文件失败 `logger.warning` 后继续（同 `session-ttl-cleanup` D4）。扫描排除 `.json.tmp`。`enforce_capacity()` 不自带定时器，是同步副作用 + 返回值的纯原语，触发由调用方负责。
**为何**：与 TTL 清理一致的鲁棒性与触发策略；session.md 触发归属待决（第 135 行），不提前耦合 cron_scheduler。CLAUDE.md「catch 后必须 log」合规。
**Alternatives**：首个失败即中断——被否，单孤儿文件阻断整轮淘汰。

## Risks / Trade-offs

- [并发 save 与 enforce_capacity 竞争（淘汰刚被重新活跃的 session）] → LRU 按 mtime 选最旧者，刚活跃的 session mtime 最新不会被选中；极端竞态下删除失败由 D5 容错吞掉，下轮自愈。
- [扫描 stat 全量文件在 session 极多时慢] → 容量管理为低频后台操作；若成为瓶颈，后续可改用 `session-metadata-index` 的索引查询替代全盘 stat（非本 change 范围）。
- [size 统计与实际磁盘占用有偏差（块对齐、文件系统开销）] → 用 `st_size`（逻辑字节）作为上限口径，对「防止无限增长」目的足够；默认上限保守（1 GB / 10000 个）。
- [两个清理能力（TTL + LRU）同时运行的交互] → 二者均为幂等纯函数、同一 mtime 口径、各自只删自己判定的文件；先后或并发运行结果收敛，无相互破坏。

## Open Questions

- 容量淘汰的触发方与触发频率（与 TTL 清理是否合并到同一后台任务）——session.md 待决问题，留作后续独立 change；本次提供的纯函数对各种调度方案均适用。
