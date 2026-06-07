## Why

CLAUDE.md 新固化的「Agent / Platform 解耦」规则禁止 agent 运行时反向依赖 platform。此前 token-tracking / token-usage-wiring / compaction-checkpoint 三项把 agent 运行时数据写进 `platform/chat_management` 的 `session_meta` 表，造成 runtime→platform 反向依赖，且 agent 独立运行时该表不存在、功能静默失效。token 与 compaction 统计本已由 observability trace（`log_run` / `log_compression`）覆盖，写 session_meta 纯属冗余。本 change 撤销这部分耦合。

## What Changes

- **撤销 token wiring**：移除 `loop.py` 的 `usage_out` 参数（run/_run_inner）、`normalizer` 的 usage_out→save 传递、`session_mgr.save` 的 `token_usage` 参数及 `add_token_usage` 调用
- **撤销 compaction 的 session_meta 写入**：移除 `runtime/context.py` 对 `update_compaction_meta` 的调用（**保留** `.pre-compact.json` 备份文件机制——它是 agent 侧、合规）
- **清理 platform 死代码**：移除 `session_admin_store` 的 `add_token_usage`、`update_compaction_meta`；从 `_COLS`/`get_meta` fallback 移除 token(2)+compaction(4) 列
- **降列 migration 058**：从 `session_meta` 删除 `total_input_tokens`、`total_output_tokens`、`last_compaction_at`、`messages_before_compaction`、`messages_after_compaction`、`compaction_summary_preview`

## Capabilities

### Modified Capabilities

- `session-compaction-checkpoint`：移除「压缩完成后更新 session_meta」「session_meta 新增压缩列」requirement；保留「压缩前写入备份文件」requirement
- `session-token-tracking`：移除全部 requirement（token 改由 observability trace 记录，session_meta 不再承载 agent 运行时 token）
- `session-token-usage-wiring`：移除全部 requirement（run usage_out 出参 + normalizer 传 save 回退）

## Impact

- **修改文件**：`runtime/loop.py`、`runtime/context.py`、`im_gateway/normalizer.py`、`session/manager.py`、`platform/chat_management/session_admin_store.py`
- **新增**：migration 058（降列）
- **删除测试**：验证 session_meta token/compaction 写入的测试（test_session_logging 的 token 部分、test_context_compaction_checkpoint 的 meta 部分、test_session_admin_store 的 token/compaction 部分、test_normalizer_token_usage）；保留备份文件相关测试
- **无消费方破坏**：尽调确认 platform 无实质消费方读这些列（admin rollup 硬编码 0、compaction 列无人读）
- **不动 resume_pending**：由后续 change `session-resume-agent-side` 迁移到 agent 侧
