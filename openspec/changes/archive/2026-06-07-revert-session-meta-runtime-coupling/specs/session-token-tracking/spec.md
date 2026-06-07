## REMOVED Requirements

### Requirement: session_meta 表新增 token 累计列

**Reason**: token 累计写入 platform 的 session_meta 违反 Agent/Platform 解耦；token 用量已由 observability trace（`loop.py` 的 `log_run(usage=...)`）覆盖。

**Migration**: migration 058 删除 `total_input_tokens` / `total_output_tokens` 列。token 统计读 observability（`observability/usage.py`）。

### Requirement: token 用量累加更新

**Reason**: `add_token_usage` 写 session_meta，随上一条 requirement 一并废弃。

**Migration**: 移除 `session_admin_store.add_token_usage`。

### Requirement: session 元数据查询返回 token 列

**Reason**: token 列删除后，`get_meta` 不再返回这些字段。

**Migration**: `get_meta` 的 `_COLS` 与 fallback 移除 token 键。

### Requirement: save 支持可选 token 用量参数

**Reason**: `session_mgr.save` 的 `token_usage` 参数仅为向 session_meta 写 token 而存在，随之回退（agent 侧不再向 platform 写 token）。

**Migration**: 移除 `save` 的 `token_usage` 参数及其调用。
