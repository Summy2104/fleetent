## Context

session 消息以单 JSON 文件全量存储。tool result 内联导致大型输出占 context、膨文件。claude-code 用 >50KB 外部化 + 引用解决。

## Goals / Non-Goals

**Goals:**
- 大型 tool result（>50KB）外部化到独立文件，session 消息存引用
- 提供 externalize / rehydrate 双向转换（纯函数，不改原列表）
- 清理 session 时连带删除外部目录

**Non-Goals:**
- 不强制在 save/load 路径接入（提供能力，wiring 渐进）
- 不外部化非 tool 消息或非字符串 content
- 不压缩外部文件（纯文本存储）

## Decisions

### D7：外部化路径与引用格式

**路径**：`SESSIONS_DIR / f"{session_id}.tool_outputs" / f"{tool_call_id}.txt"`
- 与主 session 文件同级的兄弟目录，按 session_id 隔离
- tool_call_id 作文件名，天然唯一

**引用格式**：`[stored:{tool_call_id}.txt]`
- 简短、可识别、rehydrate 可解析回 tool_call_id

**阈值**：50KB（`_TOOL_RESULT_INLINE_LIMIT = 50 * 1024`），对标 claude-code。

**纯函数**：externalize/rehydrate 返回新列表，深拷贝被改的消息，不 mutate 入参——与 message_hygiene、context 压缩的纯函数风格一致。

### D8：清理与扫描隔离

- `cleanup_expired` 跳过路径含 `.tool_outputs/` 的文件（`rglob("*.json")` 不匹配 `.txt`，但防御性跳过以防目录内有 json）
- 删除 session 主文件后，`shutil.rmtree(SESSIONS_DIR / f"{session_id}.tool_outputs", ignore_errors=True)` 连带回收
- 文件缺失时 rehydrate 保留引用占位（不报错）——容忍外部文件被独立删除

## Risks / Trade-offs

- **[风险] 外部文件与主文件不一致** → cleanup 连带删除；rehydrate 容忍缺失。两者解耦但清理同步
- **[风险] save/load 未接入则无实际效果** → 本 change 建能力；接入是后续 wiring，不破坏现状
- **[风险] tool_call_id 缺失的 tool 消息** → 无 tool_call_id 的消息跳过外部化（保持内联），不报错

## Migration Plan

无 schema 变更，纯文件操作。部署即提供能力。已有 session 无 `.tool_outputs` 目录，rehydrate 对其原样返回。
