## Why

`externalize_tool_results` / `rehydrate_tool_results` 已实现（session-tool-result-extern）但未接入 save/load 路径——大型 tool result 仍然内联进 session JSON，机制建好却未生效。本 change 把这对函数接入 `save()`（写盘前外部化）和 `load()`（读出后读回），使外部化真正发挥作用。

## What Changes

- **save() 写盘前调用 externalize_tool_results**：在序列化 messages 到 JSON 前，将超 50KB 的 tool result 外部化为引用，写盘的是引用版本
- **load() 读出后调用 rehydrate_tool_results**：从 JSON 读出 messages 后，将 `[stored:xxx]` 引用读回完整内容，调用方拿到的始终是完整 messages
- **round-trip 透明**：load → rehydrate（完整）→ agent 处理 → save → externalize（引用写盘），调用方无感知

## Capabilities

### Modified Capabilities

- `session-persistence`：`save()` SHALL 在写盘前外部化大型 tool result；`load()` SHALL 在读出后读回外部化内容

## Impact

- **修改文件**：`src/fleetent/session/manager.py`（save、load 各加一行调用）
- **无契约变更**：save/load 签名不变，调用方无感知
- **行为变更**：超 50KB tool result 实际落到 `.tool_outputs/` 而非内联 JSON——这是预期生效
- **向后兼容**：旧 session（无外部化）load 时 rehydrate 对无引用消息原样返回；新写入的 session 含引用，cleanup 已能连带清理 `.tool_outputs`
