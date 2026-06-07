## Context

session-restart-recovery（PR #139）+ session-resume-consume（PR #159）把 resume_pending 存进 platform 的 session_meta，是 agent→platform 反向依赖。token/compaction 已在返工 1（PR #163）回退。resume 是 agent 内部状态、trace 不覆盖，需迁移而非删除。

## Goals / Non-Goals

**Goals:**
- resume_pending 存储从 platform session_meta 迁到 agent 侧 `.resume` 标记文件
- agent_app / normalizer 不再 import platform
- 行为语义不变（标记→消费→清除）

**Non-Goals:**
- 不改 resume 的对外语义
- 不引入新的 agent 侧 DB（用文件，零 DB 依赖）

## Decisions

### D10：用 `.resume` 标记文件，与 `.pre-compact.json` 同模式

resume_pending 本质是布尔标记，最轻量的 agent 侧表示就是「标记文件是否存在」：

- `{session_id}.resume` 空文件存在 = pending
- mark = touch；is = exists；clear = unlink(suppress)
- scan = `_scan_sessions()` 返回的 mtime 在窗口内 → mark

**为何不用 session 文件 meta 字段**：写 meta 需重写整个 session JSON（含 messages），且会刷新 mtime（破坏「最近活跃」语义）。独立标记文件零副作用、与现有 `.pre-compact.json` / `.tool_outputs` 兄弟文件模式一致、cleanup 已有连带删除范式。

**零 DB / 零 platform**：标记完全在 `data/sessions/` 下，agent 独立运行天然可用——这正是解耦原则要求的。

### D11：cleanup 与扫描

- `cleanup_expired` 删主文件后连带 `(SESSIONS_DIR / f"{sid}.resume").unlink()`（suppress），与 `.pre-compact.json` 处理一致
- `_scan_sessions` / `cleanup_expired` 用 `rglob("*.json")`，`.resume` 后缀天然不匹配，不会被误当 session
- `scan_and_mark_recent_resume` 复用 `_scan_sessions()`（已跳过 `.json.tmp`/`.pre-compact.json`/`.tool_outputs`），只看真实 session

### D12：platform 降列

`session_meta.resume_pending` 失去 agent 写入方后是死列，migration 059 删除。`session_admin_store` 的 resume 函数（mark/clear/list/scan）随之删除，`_COLS`/fallback 去 resume_pending。

## Risks / Trade-offs

- **[风险] mark 时 touch 是否刷新被标记 session 的"最近活跃"判断** → `.resume` 是独立文件，touch 它不影响主 session 文件 mtime，扫描看的是主文件 mtime，无副作用
- **[风险] .resume 文件泄漏** → cleanup_expired 连带删除；且文件 0 字节，泄漏成本可忽略

## Migration Plan

migration 059 drop resume_pending 列。已标记的 session（platform 环境）迁移后标记丢失一次——可接受（resume 是尽力而为的运营提示，非数据正确性依赖；下次重启会基于文件 mtime 重新标记）。
