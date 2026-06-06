## Why

所有 tool result 无论大小都内联在 session JSON 中。大型工具输出（如 `read_file` 返回 1MB、`run_code` 长 stdout）占用大量 context，膨胀每次 save/load 的文件体积，且重复 round-trip 进 LLM 上下文。对标 claude-code：>50KB 的 tool result 单独持久化到磁盘，session 消息只保留引用。

## What Changes

- **session/manager.py 新增常量** `_TOOL_RESULT_INLINE_LIMIT = 50 * 1024`（50KB）
- **新增 externalize_tool_results(session_id, messages)**：遍历消息，将 `role=="tool"` 且 content 为超过 50KB 的字符串外部化——写入 `data/sessions/{session_id}.tool_outputs/{tool_call_id}.txt`（原子写），消息 content 替换为 `[stored:{tool_call_id}.txt]` 引用。返回新列表，不改原列表
- **新增 rehydrate_tool_results(session_id, messages)**：将 `[stored:xxx]` 引用读回完整 content；外部文件缺失时保留引用占位（不报错）
- **cleanup_expired 连带删除外部目录**：删除 session 主文件后，连带 `shutil.rmtree({session_id}.tool_outputs)`（best-effort）
- **扫描跳过 .tool_outputs 目录**：`cleanup_expired` 跳过路径含 `.tool_outputs/` 的文件，避免误当 session

## Capabilities

### New Capabilities

- `session-tool-result-extern`：大型 tool result 外部化规范——50KB 阈值、外部文件路径、引用占位、读回、清理

### Modified Capabilities

- `session-persistence`：清理 session 时 SHALL 连带删除其 `.tool_outputs` 外部目录

## Impact

- **修改文件**：`src/fleetent/session/manager.py`、`src/fleetent/session/__init__.py`
- **无 schema 变更**：纯文件操作
- **无破坏性变更**：新函数独立，调用方按需调用；未外部化的现有 session 不受影响（rehydrate 对无引用消息原样返回）
- **范围说明**：本 change 提供 externalize/rehydrate 能力 + 清理；在 save/load 路径的接入（何时调用）由调用方决定，渐进 wiring。详见决策文档 D7。
