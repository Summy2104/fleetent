## Context

三项改动（PR #134/#137/#160）把 compaction/token 写进 platform 的 session_meta，违反 agent/platform 解耦。token 在 `loop.py log_run(usage=)`、compaction 在 `context.py log_compression` 已进 observability trace（agent 侧）。session_meta 写入是冗余 + 违规。

## Goals / Non-Goals

**Goals:**
- 移除 token/compaction 的 agent→platform(session_meta) 写入路径
- 清理 platform 死代码与死列
- 保留 agent 侧合规机制（.pre-compact.json 备份、observability trace）

**Non-Goals:**
- 不动 resume_pending（后续 change 迁移到 agent 侧）
- 不改 observability trace（token/compaction 已在其中）
- 不改 .pre-compact.json 备份机制

## Decisions

### D1：token wiring 整条回退（含 run usage_out）

`run()`/`_run_inner` 的 `usage_out` 出参当初只为给 normalizer→save 喂 token。token 既走 trace，save 不再需要 token_usage，则 usage_out 无消费方，一并回退——避免留 dead param。

### D2：compaction 保留备份、移除 session_meta 记录

`.pre-compact.json`（agent 侧文件）是压缩可回溯的实质机制，保留。session_meta 的 compaction 列只是冗余统计（trace 已有），移除调用 + 降列。

### D3：降列安全性（已尽调）

`chat_admin_api._rollup` 的 token 统计硬编码返回 0，不读 session_meta token 列；compaction 列无 platform 消费方。get_meta 返回的 meta dict 少这些键，chat_admin_api 整体透传、不强引用键名，前端容忍缺键。故降列安全。

### D4：spec 处理

- session-compaction-checkpoint：MODIFIED——删除两条 session_meta 相关 requirement，保留备份文件 requirement
- session-token-tracking / session-token-usage-wiring：REMOVED 全部 requirement（capability 行为废弃，token 归 trace）

## Risks / Trade-offs

- **[风险] 前端展示了被删的 meta 键** → 这些列值本就多为 0/null（agent 独立运行从未真正写入）；前端 JS 容忍 undefined。低风险
- **[风险] migration 058 drop column 在旧 SQLite** → 用 Alembic batch_alter_table（重建表模式），SQLite 兼容

## Migration Plan

migration 058 batch drop 6 列。向后：已存数据的这些列被丢弃（agent 运行时数据本应在 trace，无损失）。降级（downgrade）重新 add 回 nullable 列。
