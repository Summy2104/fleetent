## Context

`runtime/context.py` 的 `compress()` 是纯内存操作：它将消息列表变换后返回新列表，调用方（`maybe_compress`、`compress_for_context_overflow`）负责将结果传回 `agent_loop.run()`，最终由 `session_mgr.save()` 落盘。压缩本身不感知 `session_id`——这是有意的设计（压缩是纯函数，不依赖持久化层）。

因此，checkpoint 必须在 **调用 `compress()` 的位置**（`maybe_compress` / `compress_for_context_overflow`）注入，而不是在 `compress()` 内部。注入点在 `loop.py` 中：`loop.py` 调用 `maybe_compress(messages, session_id=session_id)`，已有 `session_id`。

## Goals / Non-Goals

**Goals:**
- 每次压缩成功前，将原始消息 JSON 原子写入 `{session_id}.pre-compact.json`
- 压缩完成后，在 session_meta 记录压缩时间、消息数变化、摘要预览
- cleanup_expired 删除主文件时同步删除备份文件
- 所有新操作 best-effort：失败记录 warn，不阻断主流程

**Non-Goals:**
- 不提供 API 端点或 CLI 命令恢复备份（本 change 只建立文件，恢复机制属于后续独立 change）
- 不保留多次压缩历史（只保留最近一次压缩前状态）
- 不修改 `compress()` 函数签名（保持纯函数）

## Decisions

### D1：checkpoint 注入位置

`loop.py` 在调用 `maybe_compress(messages, session_id=session_id)` 前后：

```python
# 压缩前（loop.py）
session_mgr.write_compaction_checkpoint(session_id, messages)

messages = await maybe_compress(messages, session_id=session_id, ...)

# 压缩后
session_admin_store.update_compaction_meta(
    session_id,
    messages_before=before_count,
    messages_after=len(messages),
    summary_preview=_extract_summary_preview(messages),
    compacted_at=time.time(),
)
```

**为何不在 `maybe_compress` 内部注入**：`maybe_compress` 不感知 session_id（设计意图：压缩是纯算法，不依赖持久化）。在 loop.py 注入保持职责分离。

### D2：备份文件格式与路径

路径：`SESSIONS_DIR / f"{session_id}.pre-compact.json"`

格式：`{"messages": [...], "compacted_at": <timestamp>}`

原子写：与主文件一致，写 `.pre-compact.json.tmp` 再 rename。

**为何不用 session_id 子目录**：`session_id` 可能含 `/`（IM 平台格式），已由 `SESSIONS_DIR / session_id.json` 的子目录处理，`.pre-compact.json` 跟随同一路径约定：`SESSIONS_DIR / f"{session_id}.pre-compact.json"` 自然支持含 `/` 的 session_id（Path 会创建子目录）。

### D3：session_meta 列设计

| 列名 | 类型 | 约束 |
|------|------|------|
| `last_compaction_at` | REAL | NULL — 未压缩过的 session |
| `messages_before_compaction` | INTEGER | NULL |
| `messages_after_compaction` | INTEGER | NULL |
| `compaction_summary_preview` | TEXT | NULL，最多 200 字符 |

Alembic migration 用 `ALTER TABLE sessions ADD COLUMN`，SQLite 支持向现有表加 NULL 列。

### D4：cleanup_expired 删除策略

```python
# 删除主文件后
pre_compact = path.with_suffix("").with_suffix(".pre-compact.json")
if pre_compact.exists():
    with suppress(OSError):
        pre_compact.unlink()
```

**不记录额外日志**：`.pre-compact.json` 是辅助文件，删除失败不影响主流程，静默处理即可（TTL 扫描下次会再尝试通过 `rglob("*.pre-compact.json")` 清理）。

等等——`rglob("*.json")` 不会扫到 `.pre-compact.json` 吗？会。但 TTL 判断用的是 `path.stat().st_mtime`，而 `.pre-compact.json` 的 mtime 是压缩发生时的时间，不是 session 最后活跃时间，可能比主文件更旧，导致误删。因此：cleanup_expired 必须**只清理主文件**（`*.json` 但排除 `*.pre-compact.json`），然后同步删除对应的 `.pre-compact.json`。

修改扫描逻辑：
```python
for path in SESSIONS_DIR.rglob("*.json"):
    if path.name.endswith(".json.tmp"):
        continue
    if path.name.endswith(".pre-compact.json"):  # 新增：跳过备份文件
        continue
    ...
```

## Risks / Trade-offs

- **[风险] 磁盘空间翻倍（压缩频繁时）** → 备份只保留最近一次，且跟随 TTL 清理；可接受
- **[风险] 备份写入增加压缩延迟** → 消息列表写一次 JSON（同步 I/O），延迟与 `save()` 相当；可接受
- **[风险] session_id 含 `/` 时路径处理** → 与主文件同约定，Path 自动创建子目录；已有测试覆盖

## Migration Plan

Alembic migration 编号紧接现有最新版本。新列 NULL 默认值，向后兼容。部署时无需停机，已有 session 的这四列为 NULL，不影响现有查询。
