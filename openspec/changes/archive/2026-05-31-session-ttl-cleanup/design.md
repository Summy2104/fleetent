## Context

`session_mgr.py`（共 43 行）当前提供 `load()`（行 30）、`save()`（行 37，原子写 `.json.tmp → rename`）、`session_lock()`（行 24，per-session asyncio.Lock）。`SESSIONS_DIR = Path("data/sessions")`（行 13）为模块级可注入路径（测试 monkeypatch 到 `tmp_path`）。没有任何过期/清理逻辑——docs/capabilities/session.md 第 67 行明确标注「无自动清理，session 文件永久积累，磁盘持续增长」。

本 change 落实 session.md 规划项「TTL 过期与自动清理」（第 75-77 行）与验收场景 4（第 107-110 行）。它是 v1.0 session 生命周期治理的一部分，与 `session-metadata-index`（元数据索引）、`session-disk-management`（LRU 容量管理）三者互补但各自独立。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；禁止全局可变状态（TTL 阈值/路径必须可 monkeypatch 注入）；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；行长 100；TDD Hard Gate；测试 monkeypatch `session_mgr.SESSIONS_DIR → tmp_path`，绝不触碰 `data/`。

## Goals / Non-Goals

**Goals:**
- 提供 `cleanup_expired(ttl_seconds=None) -> list[str]`：一次性扫描并删除超期 session 文件，返回被删 session_id 列表。
- TTL 以**最后活跃时间**计算（文件 mtime），而非创建时间，对齐 session.md 第 77 行。
- TTL 时长经 `Settings.session_ttl_days` env 字段配置 + 调用参数覆盖。
- 删除容错（单文件失败不中断整批）、跳过 `.json.tmp` 临时文件、记录系统日志。
- 提供可被任意调度器调用的纯清理原语。

**Non-Goals:**
- 不实现后台触发调度（cron 接入 vs 独立后台任务是 session.md 待决问题，留待后续 change）。
- 不引入元数据存储（最后活跃时间复用文件 mtime；元数据索引是 `session-metadata-index` 范围）。
- 不实现总量/数量上限的 LRU 清理（那是 `session-disk-management` 范围）。
- 不改动 `load()` / `save()` / `session_lock()` 的既有行为与原子写契约。

## Decisions

### D1：最后活跃时间复用文件 mtime，不新增存储
`save()`（行 37-42）每次写入都 `tmp.replace(path)`，原子替换会刷新目标文件的 mtime。因此「最后活跃时间」直接取 `path.stat().st_mtime`，无需额外记录活跃时间戳。
**为何**：零新增存储、零 schema、与原子写天然契合；符合「不增加 session 文件本身体积」（session.md 第 81 行精神）。
**Alternatives**：①在 session 文件内写 `last_active` 字段——被否，需改 `save()` 序列化结构、与现有纯消息列表格式冲突，且重读全文件成本高；②单独维护活跃时间索引——被否，属 `session-metadata-index` 职责，本 change 不应耦合元数据存储。

### D2：TTL 经 Settings 配置 + 调用参数覆盖（对齐 context_mgr 模式）
- `config.py` 的 `Settings` 增加 `session_ttl_days: int = 30`（env 可配，与 `context_max_tokens` / `permission_gate_*_timeout_seconds` 同类）。
- `session_mgr.py` 提供 `_default_config() -> dict`：惰性 `from fleetent.config import Settings`（同 context_mgr 第 11 行做法），返回 `{"ttl_seconds": settings.session_ttl_days * 86400}`。
- `cleanup_expired(ttl_seconds: float | None = None)`：`ttl_seconds` 为 None 时回落 `_default_config()`。

解析优先级：**调用参数 > Settings（env）> pydantic 字段默认值**。测试通过传 `ttl_seconds` 或 monkeypatch `_default_config`，不实例化真 `Settings`（避免 `anthropic_api_key` 必填）。
**为何**：项目既有运行旋钮全部走 Settings env 字段；再引 YAML 既违背「无新依赖」也与现有代码割裂。Settings 字段默认值即单一事实来源。
**Alternatives**：①模块级 `DEFAULT_TTL` 常量——被否，与 Settings 默认值重复且不可 env 配；②settings.yaml——被否，文件不存在、机制不符。

### D3：扫描与删除口径
`cleanup_expired()` 只匹配 `SESSIONS_DIR.glob("*.json")`，**显式排除 `.json.tmp`**（glob `*.json` 本就不含 `.tmp`，但实现需确保不误把 `.json.tmp` 当 session）。对每个文件：`now - st_mtime > ttl_seconds` 判超期；从文件名 stem 还原 session_id。
**注意**：session_id 含 `/`（如 `u123/dm:U08XYZ`，session.md 第 55 行），文件路径为 `data/sessions/{session_id}.json`，故存在子目录层级。扫描用 `rglob("*.json")` 递归，session_id 由相对 `SESSIONS_DIR` 的路径去掉 `.json` 后缀还原。
**为何**：与 `load()`/`save()` 的路径构造（`SESSIONS_DIR / f"{session_id}.json"`）对称，正确处理带 `/` 的 session_id。
**Alternatives**：仅扫描顶层 `glob` ——被否，会漏掉子目录中的 session 文件。

### D4：删除容错与日志
逐个删除，单个 `path.unlink()` 抛异常（文件已被并发删、权限问题）时**捕获并 log.warning 后继续**，不让一个失败中断整批。成功删除记入返回列表并 log.info（含 session_id）。整批结束记一条汇总日志（删除数量）。
**为何**：清理是后台维护操作，鲁棒性优先；对齐 session.md 验收场景 4「清理操作记录在系统日志中」。CLAUDE.md「不吞异常，catch 后必须 log」——此处 catch 后 log.warning 合规。
**Alternatives**：首个失败即抛出——被否，单个孤儿文件会阻断整个清理周期。

### D5：纯清理原语，触发调度留待后续
`cleanup_expired()` 不自带定时器/后台任务，是同步副作用函数（删文件）+ 返回值。触发由调用方负责。
**为何**：session.md 待决问题（第 135 行）「TTL 清理任务由谁触发？复用 cron_scheduler 还是 session_mgr 内部后台任务？」尚未定论；本 change 先把可测试、可复用的清理原语做对，触发策略作为独立 change 决策，避免提前耦合 cron_scheduler。
**Alternatives**：本次直接接 cron_scheduler——被否，触发归属未决，且会把 session_mgr 对 cron 的依赖提前固化。

## Risks / Trade-offs

- [mtime 不可靠（如某些文件系统 mtime 精度低、或外部工具改动 mtime）] → on-premises 部署的本地磁盘 mtime 足够可靠；TTL 默认 30 天远大于 mtime 精度误差，影响可忽略。
- [清理与正在进行的 `save()` 竞争（删到一半被重写）] → cleanup 只删超期文件（30 天未活跃），活跃 session 不会被选中；极端竞态下删除失败由 D4 容错吞掉，下轮重试。
- [`.json.tmp` 孤儿文件不被清理] → 本 change 只管超期 session（`*.json`）；孤儿 tmp 清理是 session.md 第 136 行另一个待决问题，不在本范围。
- [递归 rglob 在 session 极多时慢] → 清理为低频后台操作（默认按天），扫描成本可接受；若成为瓶颈由 `session-metadata-index` 提供的索引查询替代全盘扫描。

## Open Questions

- TTL 清理的触发方（cron_scheduler vs session_mgr 内置后台任务）——session.md 待决问题，留作后续独立 change，本次提供的纯函数对两种方案均适用。
