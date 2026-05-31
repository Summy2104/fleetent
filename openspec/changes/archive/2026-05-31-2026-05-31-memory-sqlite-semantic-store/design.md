## Overview

本 change 将 memory_layer 从“自由文本 JSONL + 最近 20 条注入”改为结构化 semantic memory store。
memory_layer 只负责提取、存储、索引和检索；注入 system prompt 的职责交给后续 long-term-ctx。

## Non-Compatibility Decision

本 change 不做向后兼容：

- 删除 `load_memories()` public API。
- 删除 `data/users/{user_id}/memories.jsonl` 写入路径。
- 不导入旧 JSONL memory。
- agent_loop 不再直接加载 memory prompt。

这是 MVP 阶段的刻意取舍，避免保留旧 JSONL 与新 SQLite 双轨。

## Data Model

新增 Alembic migration：

```sql
CREATE TABLE memory_items (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  type TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at DATETIME NOT NULL,
  updated_at DATETIME NOT NULL,
  expires_at DATETIME
);

CREATE INDEX idx_memory_items_user_type ON memory_items(user_id, type);
CREATE INDEX idx_memory_items_user_expires ON memory_items(user_id, expires_at);
```

`type` 允许值：

- `identity`
- `preferences`
- `context`

`context` 默认 TTL 30 天；`identity` / `preferences` 默认无 TTL。

## Public API

```python
MemoryType = Literal["identity", "preferences", "context"]


@dataclass(frozen=True)
class MemoryItem:
    id: str
    user_id: str
    type: MemoryType
    content: str
    created_at: datetime
    updated_at: datetime
    expires_at: datetime | None


async def extract_and_update(user_id: str, conversation: list[dict[str, Any]]) -> None:
    """Extract structured memories from conversation and update store."""


async def search(user_id: str, query: str, limit: int = 10) -> list[MemoryItem]:
    """Return semantically relevant, non-expired memory items."""
```

本 change 不要求 public `upsert_memory()` / `delete_memory()`；后续 reflection 需要时再扩展。

## Extraction Contract

`extract_and_update()` 调用 `model_router.get_async_client_and_config("memory_extraction")`。

LLM 输出 JSON array：

```json
[
  {
    "action": "create",
    "type": "preferences",
    "content": "User prefers concise Chinese replies"
  },
  {
    "action": "ignore",
    "reason": "one-off formatting request"
  }
]
```

第一版只支持：

- `create`
- `ignore`

不支持：

- `update`
- `delete`
- `merge`

非法 JSON、非法 type、空 content、未知 action 均忽略，不抛到 agent_runtime。

## Write Flow

1. `extract_and_update(user_id, conversation)` flatten conversation。
2. 调 LLM 获取结构化 memory actions。
3. 对每个 `create` 生成 `MemoryItem`。
4. 写入 SQLite `memory_items`。
5. 调用 `vector_store.upsert(memory_id, content, memory_namespace(user_id))`。

如果 SQLite 写入成功但 vector_store 写入失败，本 change 应抛出错误并在测试中暴露；不做补偿队列。
后续可通过 repair job 处理一致性。

## Search Flow

1. 调用 `vector_store.search(query, memory_namespace(user_id), limit)`。
2. 按返回 id 回查 `memory_items`。
3. 过滤 `expires_at < now`。
4. 保持 vector_store 返回顺序。
5. 返回 `MemoryItem`。

若 vector_store 返回 id 但 SQLite 已无记录，则跳过该 id。

## Agent Runtime Change

agent_loop 当前直接调用 `load_memories()` 并注入 system prompt。本 change 移除该路径：

- `run()`
- `run_stream()`
- `run_sync()`
- IM normalizer 中的直接 memory load 如存在也应移除

完成后，长期记忆不会自动注入 prompt。后续 `long-term-context-orchestration` 会通过 `memory_layer.search()`
恢复注入。

## Error Handling

- LLM 提取失败：不写 memory，调用方继续。
- LLM 返回非法 JSON：不写 memory，调用方继续。
- 单条 memory action 非法：跳过该 action，继续处理其他 action。
- SQLite 或 vector_store 写入失败：抛出，测试暴露。
- search query 为空：允许调用，具体结果由 vector_store 决定。

## Testing

本 change 按 TDD 执行，重点测试：

- migration 创建 `memory_items` 表和索引。
- `extract_and_update()` 写入 identity / preferences / context。
- context 默认 expires_at 为 now + 30 days。
- identity / preferences expires_at 为 NULL。
- `ignore` action 不写入。
- 非法 LLM 输出不写入且不抛到 agent_runtime。
- 写入 memory 后调用 vector_store.upsert。
- search 使用 vector_store ids 回查 SQLite，并过滤过期记忆。
- search 保持 vector_store 排序。
- agent_loop 不再调用 `load_memories()`。
- `load_memories()` 不再作为 public API 存在。
- 不创建或追加 `data/users/{user_id}/memories.jsonl`。

## Future Work

后续独立 changes：

- `long-term-context-orchestration`
- `memory-conflict-resolution`
- `memory-reflection-cleanup`
- `memory-admin-view`
