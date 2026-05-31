## 0. 前置确认

- [ ] 0.1 确认本 change 依赖 `2026-05-31-vector-store-foundation` 完成后再实现
- [ ] 0.2 确认本 change 不兼容旧 JSONL memory，不导入旧文件，不保留 `load_memories()`
- [ ] 0.3 确认本 change 不做 long-term-ctx 注入、不做冲突合并、不做 reflection 清理

## 1. memory_items migration

- [ ] 1.1 Write failing tests: Alembic upgrade 后存在 `memory_items` 表和必要索引
- [ ] 1.2 新增 Alembic migration 创建 `memory_items`
- [ ] 1.3 运行 `uv run pytest -x -q`，确认 1.1 红测转绿

## 2. Public API 与 legacy 删除

- [ ] 2.1 Write failing tests: `MemoryItem`、`extract_and_update`、`search` 可导入；`load_memories` 不再可导入
- [ ] 2.2 修改 memory_layer public API，删除旧 JSONL `load_memories`
- [ ] 2.3 运行 `uv run pytest -x -q`，确认 2.1 红测转绿

## 3. Extraction JSON contract

- [ ] 3.1 Write failing tests: LLM 返回 `create` action 时写入结构化 memory；`ignore` action 不写入
- [ ] 3.2 实现 `extract_and_update()` 的 LLM 调用和 JSON 解析
- [ ] 3.3 运行 `uv run pytest -x -q`，确认 3.1 红测转绿

## 4. TTL 与类型规则

- [ ] 4.1 Write failing tests: context 默认 expires_at = now + 30 days；identity/preferences expires_at 为 NULL；非法 type 被忽略
- [ ] 4.2 实现 MemoryType 校验和 TTL 规则
- [ ] 4.3 运行 `uv run pytest -x -q`，确认 4.1 红测转绿

## 5. SQLite 写入与 vector_store upsert

- [ ] 5.1 Write failing tests: create action 写入 `memory_items` 后调用 `vector_store.upsert(memory_id, content, memory_namespace(user_id))`
- [ ] 5.2 实现 SQLite 写入和 vector_store 同步索引
- [ ] 5.3 运行 `uv run pytest -x -q`，确认 5.1 红测转绿

## 6. Search API

- [ ] 6.1 Write failing tests: `search()` 调用 vector_store.search，按返回 ids 回查 SQLite，过滤过期 memory，并保持 vector_store 顺序
- [ ] 6.2 实现 `search(user_id, query, limit)`
- [ ] 6.3 运行 `uv run pytest -x -q`，确认 6.1 红测转绿

## 7. agent_loop 移除旧注入路径

- [ ] 7.1 Write failing tests: `agent_loop.run()` / `run_stream()` / `run_sync()` 不再调用 `load_memories` 或直接注入 memory prompt
- [ ] 7.2 修改 agent_loop 和相关 IM normalizer 调用点，移除直接 memory prompt 注入
- [ ] 7.3 运行 `uv run pytest -x -q`，确认 7.1 红测转绿

## 8. 不写 JSONL

- [ ] 8.1 Write failing tests: `extract_and_update()` 不创建或追加 `data/users/{user_id}/memories.jsonl`
- [ ] 8.2 移除旧 JSONL memory 写入路径和旧测试
- [ ] 8.3 运行 `uv run pytest -x -q`，确认 8.1 红测转绿

## 9. 收尾验证

- [ ] 9.1 运行 `uv run pytest -x -q`
- [ ] 9.2 运行 `uv run ruff format src tests`
- [ ] 9.3 运行 `uv run ruff check src tests`
- [ ] 9.4 运行 `uv run mypy src`
- [ ] 9.5 运行 `openspec validate 2026-05-31-memory-sqlite-semantic-store`
