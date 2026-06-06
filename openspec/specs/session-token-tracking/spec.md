# session-token-tracking Specification

## Purpose
Per-session cumulative token usage (input/output) persisted in session_meta for admin console consumption reporting.

## Requirements

### Requirement: session_meta 表新增 token 累计列

`session_meta` 表 SHALL 新增两列：`total_input_tokens`（INTEGER，default 0）、`total_output_tokens`（INTEGER，default 0），通过 Alembic migration 添加。现有行默认为 0。

#### Scenario: migration 添加 token 列
- **WHEN** 运行数据库 migration
- **THEN** `session_meta` 表新增 `total_input_tokens` 和 `total_output_tokens` 两列，现有行值为 0

#### Scenario: 新列默认 0
- **WHEN** 升级后查询一个无 token 记录的历史 session 元数据
- **THEN** `total_input_tokens` 和 `total_output_tokens` 返回 0，不报错

### Requirement: token 用量累加更新

系统 SHALL 提供 `add_token_usage(session_id, input_tokens, output_tokens)` 函数，对指定 session 的 token 列执行累加更新（`total_input_tokens += input_tokens`，`total_output_tokens += output_tokens`）。函数 MUST 在 session_meta 行不存在时先创建（origin 默认 web），确保累加目标存在。

#### Scenario: 累加 token 用量
- **WHEN** 对同一 session 连续调用 `add_token_usage(sid, 100, 50)` 两次
- **THEN** 该 session 的 `total_input_tokens` 为 200，`total_output_tokens` 为 100

#### Scenario: 首次调用自动创建行
- **WHEN** 对一个 session_meta 中尚无行的 session 调用 `add_token_usage`
- **THEN** 自动创建该 session 的元数据行并写入 token 值，不报错

### Requirement: session 元数据查询返回 token 列

`get_meta(session_id)` SHALL 在返回值中包含 `total_input_tokens` 和 `total_output_tokens`。

#### Scenario: get_meta 包含 token 字段
- **WHEN** 查询一个有 token 记录的 session 元数据
- **THEN** 返回值包含 `total_input_tokens` 和 `total_output_tokens` 字段

### Requirement: save 支持可选 token 用量参数

`session_mgr.save` SHALL 接受可选参数 `token_usage: tuple[int, int] | None = None`。当非 None 时，MUST 调用 `add_token_usage` 累加 token；调用 MUST 为 best-effort——失败记 warn 日志，MUST NOT 阻断 session 消息持久化。当为 None 时行为与改动前一致。

#### Scenario: save 携带 token 时累加
- **WHEN** 调用 `save(session_id, messages, token_usage=(120, 80))`
- **THEN** session 消息正常持久化，且该 session 的 token 列累加 120/80

#### Scenario: token 更新失败不阻断持久化
- **WHEN** `save` 携带 token_usage 但 token 更新抛出异常
- **THEN** 异常被记录为 warn 日志，session 消息文件已成功写入不回滚

#### Scenario: 不传 token 参数时行为不变
- **WHEN** 调用 `save(session_id, messages)` 不传 token_usage
- **THEN** 行为与改动前完全一致，不触碰 token 列
