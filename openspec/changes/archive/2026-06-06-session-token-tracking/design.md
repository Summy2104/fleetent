## Context

两个表保存 session 元数据：
- `sessions`（index.py）：用 `CREATE TABLE IF NOT EXISTS` 自建，**不归 Alembic**，存 message_count、时间戳
- `session_meta`（session_admin_store.py，migration 022 创建）：**Alembic 管理**，存 origin/status/takeover/pinned，P0-3 已加压缩列

## Goals / Non-Goals

**Goals:**
- session 级累计 token（input/output）持久化，可按 session 查询
- 累加语义：反映会话全生命周期总消耗
- best-effort：token 更新失败不阻断 session 持久化

**Non-Goals:**
- 不计算成本（cost）——需要 per-model 定价表，属于后续 change
- 不改 loop 强制传 token——save 支持参数即可，wiring 由调用方决定
- 不动 index.py 的 sessions 表

## Decisions

### D4：token 列加到 session_meta（Alembic）而非 index.py sessions 表

**决策**：token 列加到 `session_meta`（Alembic migration 055），不加到 index.py 的 `sessions` 表。

**理由**：
- index.py 的 `sessions` 表用 `CREATE TABLE IF NOT EXISTS` 自建，不在任何 Alembic migration 中。若用 migration 055 `ALTER TABLE sessions`，全新 DB 只跑 migration（不跑 index.py 的 _init_db）时表不存在会失败
- CLAUDE.md 明确「schema lifecycle 归 Alembic」「不要复制 _init_db 建表/补列模式」
- 与 P0-3 一致：compaction meta 也加在 session_meta
- session_admin_store 已在 P0-3 验证为可用的 Alembic 表写入路径

**代价**：token 与 message_count 分处两表。但两者都按 session_id 主键，查询可 join；运营查询走 session_admin_store 即可。

### D5：累加而非覆盖

`add_token_usage` 用 `SET x = COALESCE(x,0) + :delta`，每次 LLM 调用的增量累加，反映会话总消耗。覆盖式（SET x = :total）需要调用方维护总数，违背「session 级累计」目标。

## Risks / Trade-offs

- **[风险] token 与 message_count 分表** → 主键一致，可 join；运营查询统一走 session_admin_store
- **[风险] save 调用方需传 token 才生效** → 本 change 只提供能力，wiring 渐进；默认 None 不破坏现有调用

## Migration Plan

migration 055 加两列 default 0，向后兼容。已有 session_meta 行的 token 列为 0（无历史 token 数据可回填，接受）。
