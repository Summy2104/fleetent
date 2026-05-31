## Why

fleetent 当前 memory_layer 仍使用 `data/users/{user_id}/memories.jsonl` 保存自由文本记忆，并在
agent_loop 启动时直接加载最近 20 条注入 system prompt。这个模式有几个问题：

- 记忆没有结构化类型，无法区分 identity / preferences / context。
- 检索是最近 N 条，不是按当前 query 相关度检索。
- JSONL 不适合过期过滤、后续 reflection 清理和质量优化。
- agent_loop 直接负责记忆注入，和 long-term-ctx 的目标边界冲突。

本 change 将 memory_layer 切到 SQLite semantic memory store，并通过 vector_store 建立向量索引。
由于当前仍处 MVP 阶段，本 change 不保留旧 JSONL 兼容，不导入旧文件。

## What Changes

- 新增 `memory-layer` 能力规范，定义结构化语义记忆。
- 新增 SQLite `memory_items` 表，由 memory_layer owns。
- 定义 `MemoryItem` 和 `MemoryType`。
- 新增 `extract_and_update(user_id, conversation)`：
  - 调用 `model_router` 的 `memory_extraction` task。
  - LLM 输出结构化 JSON，动作只支持 `create` / `ignore`。
  - 写入 `memory_items`。
  - 同步写入 vector_store，namespace 使用 `mem:{user_id}`。
- 新增 `search(user_id, query, limit=10)`：
  - 通过 vector_store 查相关 memory ids。
  - 回查 SQLite。
  - 过滤已过期 context 记忆。
- 删除旧 JSONL memory 语义：
  - 不保留 `data/users/{user_id}/memories.jsonl` 写入。
  - 不导入旧 JSONL memory。
  - 删除或停止导出 `load_memories()`。
  - agent_loop 不再直接注入最近 20 条 memory。

## Capabilities

### New Capabilities

- `memory-layer`：结构化 per-user semantic memory 存储、提取、向量索引和检索。

### Modified Capabilities

- `agent-runtime`：移除直接 memory prompt 注入；长期上下文注入后续由 long-term-ctx 接回。

## Dependencies

- 依赖 `2026-05-31-vector-store-foundation` 完成后再实现。
- 依赖现有 database-runtime 和 Alembic migration。

## Impact

- **代码**：
  - 修改 `memory_layer`，从 JSONL 改为 SQLite + vector_store。
  - 修改 agent_loop，移除 `load_memories()` 直接注入。
  - 删除或重写旧 JSONL memory tests。
- **数据**：
  - 新增 `memory_items` 表。
  - 不迁移旧 `data/users/*/memories.jsonl`。
- **行为变化**：
  - 本 change 完成后，agent 暂时不会自动注入长期记忆。
  - 长期上下文注入将在后续 `long-term-context-orchestration` change 中恢复。
- **不包含**：
  - 不做旧 JSONL 导入。
  - 不做复杂冲突合并、更新、删除或 merge。
  - 不做 reflection 清理。
  - 不做 memory UI。
  - 不做 long-term-ctx 注入。
