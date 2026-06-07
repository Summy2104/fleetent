## Context

内置 `todo` 工具（`tools/interaction_tools.py`）当前用模块级 dict `_todo_store` 维护 session 级任务列表：进程重启即丢、无完成状态、上下文压缩会丢、且违反「禁全局可变状态」。

约束：agent 与 platform 完全解耦（PR #163/#164 刚清除全部 runtime→platform 依赖），任何持久化必须纯 agent 侧。`session/manager.py` 已确立「兄弟文件」范式存放 agent 侧 per-session 运行态：`.pre-compact.json`（压缩快照）、`.resume`（resume 标记）、`.tool_outputs/`（外置 tool 结果）。session 设计文档 D10 明确否决用 session JSON `meta` 存此类状态（写 meta 要重写整个 JSON + 刷新 mtime，破坏「最近活跃」语义）。

## Goals / Non-Goals

**Goals:**
- todo 升级为带状态机的持久化任务清单，跨进程重启存活，纯 agent 侧。
- 复用既有兄弟文件范式与原子写约定，零新依赖、零 DB 表、零 platform 依赖。

**Non-Goals:**
- 不做压缩侧「active-task 逐字保留/注入上下文」（后续 C3a）。
- 不引入跨 session 共享或多用户聚合（todo 严格 per-session）。
- 不改 `clarify` 工具。

## Decisions

### D1：持久化用 agent 侧兄弟文件 `{session_id}.todo`（不用 meta、不用 platform）

权威状态存 `SESSIONS_DIR/{session_id}.todo`，内容为 JSON（条目数组）。与 `.resume`/`.pre-compact.json` 同模式。
- **为何不用 session JSON `meta`**：沿用 session 设计文档 D10——写 meta 需重写整个 session JSON（含 messages）且刷新主文件 mtime，破坏 TTL/容量的「最近活跃」判定。独立兄弟文件零副作用。
- **为何不用 platform `session_meta` 表**：runtime→platform 反向依赖，PR #163 已回退此类耦合；agent 独立运行时该表不存在。
- **后缀选 `.todo`（不带 `.json`）**：`_scan_sessions()`/`cleanup_expired()` 用 `rglob("*.json")`，`.todo` 天然不匹配，不会被误当 session 计数/淘汰/过期（与 `.resume` 选非 `.json` 后缀同理）。

### D2：原子写、不取 `session_lock`（lock-free）

`write_todo` 用 `tmp→replace` 原子写，**不**获取 `session_lock`。
- **为何不取锁**：IM 路径 `normalizer` 在 `session_lock` 内包住整个 run，而 todo 工具在 run *内部*被 dispatch；工具再取同一 `session_lock`（asyncio.Lock 不可重入）会死锁。`write_compaction_checkpoint`/`mark_resume_pending` 同样在 run 内被调、同样 lock-free 原子写——直接沿用该范式。
- **并发正确性**：同一 session 的 run 在 IM 路径已被 run 级 session_lock 串行；原子 `replace` 保证无半写态。极少数并发（如 TUI 同 session 并发）下退化为「整列表 last-writer-wins」，对任务清单可接受。

### D3：条目结构与单 in_progress 不变式

条目 `{"id": str, "text": str, "status": "pending"|"in_progress"|"completed"}`。`id` 为列表内唯一短串（如序号 `"1"`、`"2"`，`set` 时分配）。
- `update` 将某条目置 `in_progress` 时，若已有其它条目处于 `in_progress`，**拒绝**并返回提示（需先完成当前进行中条目）——保持「至多一个进行中」不变式清晰、可测，避免隐式自动降级带来的状态歧义。

### D4：向后兼容的 `set`

`set` 仍接受 `items: list[str]`，每项自动赋 `id` + `pending`，保证旧用法不破。`update` 新增 `item_id` + `status` 两个参数。`get` 渲染为带状态的可读文本。

### D5：无 `session_id` 降级

无 `session_id`（无会话一次性调用）时，todo 退化为进程内临时列表（不写文件、不报错），保持现有「无会话也能用」的体验。

## Risks / Trade-offs

- **[Risk] `enforce_capacity()`（LRU 容量淘汰）只删主 `.json`、不连带删兄弟文件** → 现状对 `.resume`/`.pre-compact.json` 已如此（团队接受：0~小字节、低成本泄漏）。`.todo` 同样小，遵循同一权衡；TTL 路径 `cleanup_expired()` 会连带删除。不在本 change 扩大到修 `enforce_capacity` 的既有行为。
- **[Risk] 旧 session 无 `.todo` 文件** → `read_todo` 文件不存在时返回空列表，天然兼容。
- **[Risk] `.todo` 内容损坏（手工编辑/截断）** → `read_todo` 解析失败时返回空列表并 warn，不破坏 run。
- **[Trade-off] last-writer-wins 而非细粒度合并** → 任务清单是低频、小数据的 scratch，整列表替换语义足够，换取实现简单与无锁。

## Open Questions

无（范围明确，落点已核到当前 main 代码）。
