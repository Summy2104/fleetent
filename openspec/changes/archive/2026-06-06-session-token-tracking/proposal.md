## Why

Token 用量目前只在 trace/observability 层记录，session 元数据没有累计 token 数或成本。管理控制台和运营监控无法按 session 查看消耗、识别高成本会话。对标 hermes-agent（`SessionEntry.input_tokens/output_tokens/estimated_cost_usd`）和 openclaw（`totalTokens + freshness`）均在 session 级持久化 token。

## What Changes

- **session_meta 表新增两列**：`total_input_tokens`（INTEGER，default 0）、`total_output_tokens`（INTEGER，default 0），通过 Alembic migration 055
- **session_admin_store 新增 add_token_usage 函数**：累加式更新 `total_input_tokens += ?, total_output_tokens += ?`（单调递增，反映会话全生命周期消耗）
- **session_admin_store.get_meta 返回值包含 token 列**
- **session_mgr.save 新增可选参数 token_usage**：`token_usage: tuple[int, int] | None = None`，非 None 时调用 `add_token_usage`（best-effort，失败记 warn 不阻断持久化）

## Capabilities

### New Capabilities

- `session-token-tracking`：session 级 token 累计规范——列定义、累加语义、best-effort 更新、查询

### Modified Capabilities

（无既有 capability 行为变更——纯增量元数据）

## Impact

- **修改文件**：`src/fleetent/platform/chat_management/session_admin_store.py`、`src/fleetent/session/manager.py`
- **新增文件**：Alembic migration `055_add_session_token_columns.py`
- **无破坏性变更**：新列 default 0，`save` 新参数默认 None，现有调用方零改动
- **设计说明**：token 列加到 session_meta（Alembic 管理）而非 index.py 的 sessions 表（后者用 CREATE TABLE IF NOT EXISTS 自建，不归 Alembic，无法用 migration ALTER）。详见决策文档 D4。
