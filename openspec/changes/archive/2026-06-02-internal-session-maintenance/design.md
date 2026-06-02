## Context

`session_mgr.py` 已有完整的清理原语与一个**被动触发**入口：
- `cleanup_expired()`（行 69）：扫 `SESSIONS_DIR` 删 mtime 超 TTL 的 session 文件，返回删除的 session_ids。
- `enforce_capacity()`：按 `session_max_total_mb` / `session_max_count` 驱逐，返回被驱逐 session_ids。
- `maybe_run_maintenance(*, _now=None) -> list[str]`（行 38）：带 `session_cleanup_interval_seconds` 时间门（模块级 `_last_cleanup_at`），门开则跑 TTL + 容量两遍、返回本轮移除的 session_ids，门关返回 `[]`。
- `save()`（行 ~275）：持久化后在 try/except 中调 `maybe_run_maintenance()` 并 `await _release_sandboxes(removed)`（SB2：回收被移除 session 的 sandbox 容器）——**此被动触发路径含 SB2 release 接线，本 change 不动**。

缺口：`maybe_run_maintenance` 只在 `save()` 被调时才有机会运行。长期无 session 写入（空闲服务、低峰、长会话间隙）时，即便时间门早已到期，清理也不会发生——过期 session 不删、磁盘不驱逐。

照搬范式：MCP 域 MCP3 健康探活（mcp_client.py）已用进程内常驻 asyncio 任务实现周期触发，且明确不挂 cron：
- `_health_monitor_loop(interval)`（行 417）：`while True: await asyncio.sleep(interval); 探活`。
- `start_health_monitor(*, interval=_PROBE_INTERVAL) -> asyncio.Task[None]`（行 425）：幂等（已在跑则返回现有 task）、`asyncio.create_task`、存模块级 `_health_monitor_task`（行 49）。
- `stop_health_monitor()`（行 438）：cancel + `with suppress(asyncio.CancelledError): await task` + 句柄置 None；无任务 no-op。
- 接入 `server.py` lifespan：启动段 `mcp_client.start_health_monitor()`（行 127），关停段 `await mcp_client.close()`（行 149，内部 cancel 探活任务）。

约束（CLAUDE.md）：禁止 AI 框架；禁止 ORM；**禁止全局可变状态滥用**（任务句柄须可注入/重置——MCP3 `_health_monitor_task` 已立此款，acceptable）；不吞异常（循环内 warning 后继续）；行长 100；mypy strict；TDD Hard Gate；测试用 `SESSIONS_DIR` monkeypatch 隔离、注入短 interval / mock `asyncio.sleep`、用 cancel 验证停止无残留、不真实长 sleep；测试落在 `tests/test_session_mgr.py`。

## Goals / Non-Goals

**Goals:**
- 让 session 清理按 `session_cleanup_interval_seconds` **主动周期触发**，不再仅依赖 `save()` 被动触发——补上"长期无活动漏清"缺口。
- 严格照搬 MCP3 范式：进程内常驻 asyncio loop + 幂等 start + 取消无残留 stop + 模块级任务句柄（可测试 reset）。
- 复用既有 `maybe_run_maintenance`（含时间门 + TTL + 容量 + SB2 release），触发器只负责"按 interval 周期调它"。
- 单次清理失败不杀常驻任务（warning 后继续循环）。
- 启停接入 server lifespan；CLI 一次性进程不启常驻任务。

**Non-Goals:**
- 不改清理语义：`maybe_run_maintenance` / `cleanup_expired` / `enforce_capacity` 的 TTL 判定、容量驱逐逻辑均不变。
- 不动 `save()` 被动触发路径与其 SB2 release 接线。
- 不引入 `cron_scheduler` / APScheduler 或任何用户级定时任务能力（与 scheduling 域解耦）。
- 不新增配置项（复用既有 `session_cleanup_interval_seconds`）。
- 不引入任何新依赖。

## Decisions

### D1：进程内常驻 asyncio 任务，**非 cron**（引 MCP3 先例 + lead 定调）
周期触发用 session_mgr 域内自持的裸 `asyncio` 后台任务实现（`asyncio.create_task` + 循环内 `await asyncio.sleep(interval)`），**MUST NOT** 走 `cron_scheduler` / APScheduler。
**为何**：① lead 定调——定时任务用内部机制，agent 全功能为一个原子自实现，不耦合张亮的 scheduling 域（其 cron 触发器 roadmap 已决定暂缓）；② MCP3 健康探活已立同款先例（mcp_client.py 行 417-446）：服务级常驻 asyncio task、绑 lifespan、零新依赖、零跨域耦合；③ 清理触发是基础设施级的内部维护，与"用户级定时任务"功能正交——用裸 asyncio task 让本机制自包含在 session_mgr 域内，既不被"调度器暂缓"波及，也不给 scheduling 域增加耦合。
**Alternatives**：①挂 `cron_scheduler` / APScheduler——被否，跨域耦合、被"调度器暂缓"波及，违 lead 定调；②保持只在 `save()` 被动触发——被否，这正是要修的缺口（长期无活动漏清）。

### D2：复用 `maybe_run_maintenance`，loop interval 默认 = `session_cleanup_interval_seconds`
循环每轮调既有 `maybe_run_maintenance()`，**不**重新实现 TTL/容量/SB2 release。loop interval 缺省取 `Settings().session_cleanup_interval_seconds`，与 `maybe_run_maintenance` 内部时间门同源同值。
**为何**：`maybe_run_maintenance` 已封装时间门 + TTL + 容量 + SB2 release（被动路径已验证）；触发器只补"何时调它"，复用 = 单一事实来源、零语义重复、不破既有用例。loop interval 与时间门同值即可：循环每到 interval 调一次，时间门此刻恰好开（自上次≥interval），两者天然对齐；即便偶有时间门关（返回 `[]`），下一轮也会补上，行为正确且无副作用。
**关于 SB2 release**：被动路径在 `save()` 里对 `maybe_run_maintenance` 返回的 removed ids 调 `_release_sandboxes`。本 change 的 loop 直接调 `maybe_run_maintenance()`（与现有时间门串行，二者不会在同一 interval 内重复实跑清理——谁先到门谁跑、另一个拿 `[]`）。本 change 范围限定为"周期触发既有入口"，不在 loop 里复制 SB2 release 逻辑；session-scope sandbox 的回收仍由 `save()` 路径承担（绝大多数场景 save 紧随活动而来）。这一取舍写明于此，保持"不动 save()/SB2 接线、不重复实现清理语义"的边界。
**Alternatives**：①loop 内复制 SB2 release——被否，重复 save() 已有逻辑、扩大改动面、违"复用不重写"；②loop interval 独立于时间门取另一值——被否，无必要且易制造"循环到点但门未开"的空跑窗口，同源最省心。

### D3：单次清理失败不杀常驻循环（warning 后继续，不吞异常）
`_session_maintenance_loop` 每轮把 `maybe_run_maintenance()` 包进 try/except：捕获异常 → `logger.warning(...)` 记录 → **continue 下一轮**，绝不让一次失败让 `create_task` 出来的常驻任务 die。
**为何**：常驻后台任务若因单次清理异常（如某 session 文件被占用、磁盘瞬时错误）而终止，会**静默丧失**之后所有周期清理——比"漏清"更隐蔽危险。CLAUDE.md「不吞异常」要求 catch 后 log 或 re-raise——这里 re-raise 会杀任务，故选 log（warning），符合既有 `save()` 维护触发 `logger.warning("session_maintenance_trigger_failed", ...)` 的同款故障隔离口径。
**Alternatives**：①不 try/except，异常逸出杀任务——被否，丧失后续所有清理；②catch 后 re-raise——被否，等于杀任务；③catch 后静默 pass——被否，违"不吞异常"。

### D4：CLI 一次性进程不启常驻任务（同 MCP3）
仅 `server.py` lifespan 调 `start_session_maintenance()`。CLI 路径（`agent_loop.run_sync`，行 1166）**不**调，与 MCP3 `start_health_monitor` 仅在 server lifespan 调、CLI `run()` 不常驻探活同理。
**为何**：CLI 是一次性短命进程，跑完即退；常驻清理循环对它无意义（还会拖住进程退出）。CLI 期间若有 `save()`，被动触发已足够。这与 skill scan「服务启动时 lifespan 跑、CLI 每次调用跑」的分工一致——常驻型行为只在 server 端。
**Alternatives**：①CLI 也启常驻 loop——被否，一次性进程无需常驻、且会妨碍退出。

### D5：模块级任务句柄 `_maintenance_task`，幂等启停（同 MCP3 `_health_monitor_task`）
模块级 `_maintenance_task: asyncio.Task[None] | None = None`。`start_session_maintenance` 幂等（`_maintenance_task is not None and not done()` 则返回现有 task）；`stop_session_maintenance` cancel + `await` 并 `with suppress(CancelledError)` + 句柄置 None，无任务 no-op。
**为何**：CLAUDE.md「禁止全局可变状态滥用」要求模块级路径/句柄可 monkeypatch 注入/重置——MCP3 `_health_monitor_task` 已是同款被接受的先例（测试中可 reset），本 change 照搬即 acceptable。幂等避免 lifespan 重入或测试重复 start 时建出多个孤儿任务；stop 的 suppress + 置 None 保证取消干净、无残留（测试可断言 `task.done()` 且句柄为 None）。
**Alternatives**：①不要句柄、每次新建 task——被否，无法幂等、无法干净 stop、会泄漏任务；②把句柄塞进某对象实例——被否，session_mgr 是模块级函数式风格（同 MCP3），无现成宿主对象，模块级句柄 + 可注入即满足约束。

## Risks / Trade-offs

- [常驻 loop 在测试中真实 sleep 拖慢测试] → interval 可注入极短值（如 0.01s）或 mock `asyncio.sleep`/`maybe_run_maintenance` 驱动循环；用 cancel 验证停止，不真实长 sleep（参考 MCP3 `start_health_monitor(interval=0.01)` 与 permission_gate 短超时）。
- [loop 与 save() 被动触发同时跑清理] → 二者都经 `maybe_run_maintenance` 的同一时间门串行：同一 interval 内谁先到谁实跑、另一个拿 `[]`，不会重复删除/驱逐；无竞态风险。
- [loop 直接调 maybe_run_maintenance 不做 SB2 release，可能漏回收 sandbox] → D2 已记取舍：session-scope sandbox 回收仍由 save() 路径承担（save 通常紧随活动）；本 change 严守"只周期触发、不重复 save() 逻辑"边界。若后续需 loop 也回收，可在独立 change 中把 release 提取为共享 helper，本次不扩面。
- [单次清理异常杀掉常驻任务、之后静默不再清理] → D3：每轮 try/except + warning + 继续循环，一次失败不杀任务；加用例断言"一次抛异常后循环仍继续触发"。
- [lifespan 重入或重复 start 建多个孤儿任务] → D5：start 幂等（已在跑返回现有 task）；加用例断言重复 start 不建第二个任务、stop 后无残留。

## Open Questions

无。interval 取既有 `session_cleanup_interval_seconds`、范式照搬 MCP3、SB2 取舍已在 D2 锁定。
