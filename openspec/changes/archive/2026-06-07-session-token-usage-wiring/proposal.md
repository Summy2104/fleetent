## Why

`session_mgr.save` 已支持 `token_usage` 参数（session-token-tracking），但调用方从不传——token 累计列永远是 0，机制建好却无数据。本 change 把 agent loop 的实际 token usage 接入：`run()` 暴露 usage，normalizer 把它传给 `save()`，使 session 级 token 累计真正生效。

## What Changes

- **run() 新增可选参数 `usage_out: list | None = None`**：run 正常完成拿到 usage 后，若 `usage_out` 非 None，append `(prompt_tokens, completion_tokens)`。不改返回类型（仍返回 str）
- **normalizer 接入**：调 `run()` 前建空 `usage_out`，传入；`save()` 时传 `token_usage=usage_out[0] if usage_out else None`
- **零破坏**：`run()` 新参数默认 None，run_sync/cron/sub_agent/测试等现有调用方完全不受影响

## Capabilities

### New Capabilities

- `session-token-usage-wiring`：token usage 从 agent loop 接入 session 持久化的规范——run usage_out 出参、normalizer 传 token_usage

## Impact

- **修改文件**：`src/fleetent/runtime/loop.py`（run 加参数 + 填充）、`src/fleetent/im_gateway/normalizer.py`（建 usage_out + 传 save）
- **无破坏性变更**：run() 返回类型不变（D9 关键决策——避免破坏大量 run() 调用方），新参数可选默认 None
- **行为生效**：IM 路径的 session 现在会累计真实 token 用量到 session_meta
- **范围**：仅 IM 路径（normalizer）；run_sync（CLI）等其他调用方不传 usage_out，行为不变
