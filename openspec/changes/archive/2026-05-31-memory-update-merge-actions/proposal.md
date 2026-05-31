## Why

`memory-layer` foundation 已经把旧 JSONL 记忆切换为 SQLite `memory_items` + `vector_store`，
但 `extract_and_update()` 目前只支持 `create` / `ignore`。这会导致用户事实变化时只能追加新条目，
无法替换旧身份、刷新临时状态或删除用户明确要求忘记的内容。

本 change 让 memory extraction 在同一次模型判断中看到有限的已有 memory snapshot，并输出
`create` / `update` / `delete` / `ignore` actions。目标是先补上结构化维护能力，避免 memory
无限追加和明显冲突；提取质量评估、真实 embedding 和 reflection 自动维护另拆后续 specs。

## What Changes

- 扩展 `extract_and_update()` 的 action contract：
  - `create`：新增 memory item。
  - `update`：更新已有 memory item 的 `content`、`updated_at` 和 `expires_at`。
  - `delete`：删除已有 memory item。
  - `ignore`：忽略一次性请求、无价值事实或不确定内容。
- 在 memory extraction prompt 输入中加入用户现有 memory snapshot：
  - `identity`：最多 20 条，按 `updated_at DESC`。
  - `preferences`：最多 30 条，按 `updated_at DESC`。
  - `context`：最多 20 条，必须未过期，按 `updated_at DESC`。
  - 总量最多 70 条，不把全部历史 memory 无界传入模型。
- 要求 `update` / `delete` action 携带 `target_id`，且 `target_id` 必须属于当前用户 snapshot。
- 同步维护 vector index：
  - `create` 后调用 `vector_store.upsert(new_id, content, mem:{user_id})`。
  - `update` 后调用 `vector_store.upsert(target_id, new_content, mem:{user_id})`。
  - `delete` 后调用 `vector_store.delete(target_id, mem:{user_id})`。
- 明确 type 行为：
  - `identity` / `context` 与已有事实冲突时优先 `update`，不追加矛盾条目。
  - `context` 被 update 时刷新 30 天 TTL。
  - `preferences` 只记录明确长期偏好；一次性请求必须 `ignore`。
- 保持 public API 不变：仍只暴露 `MemoryItem`、`extract_and_update()`、`search()`。

## Module Boundary Impact

- **owning package**：`intelligence.memory_layer`（当前代码仍在 legacy `memory_layer.py`，不在本 change 做目录迁移）。
- **public API surface**：不新增 public API；扩展 `extract_and_update()` 内部 action contract。
- **owned tables**：继续使用 `memory_items`，无 schema 变更。
- **config namespace**：无新增配置；snapshot limits 先用模块内可注入常量。
- **cross-module dependencies**：继续依赖 `model_router` 和 `vector_store` public API。
- **migration / shim plan**：无迁移；不恢复旧 JSONL 兼容，不新增 shim。

## Impact

- **代码**：
  - 修改 `memory_layer.extract_and_update()` prompt 输入和 action 处理。
  - 新增内部查询 / 更新 / 删除 helper。
- **测试**：
  - 新增 unit tests，mock LLM 和 vector_store，验证 create / update / delete / ignore 行为。
  - 验证 snapshot 限额和 context 过期过滤。
- **数据**：无 schema 变更。
- **不包含**：
  - 不做 `memory-extraction-evaluation`。
  - 不做 memory compaction / retention 上限。
  - 不做 reflection 自动写回 memory。
  - 不做真实 embedding provider。
  - 不改 long-term-ctx 注入策略。
