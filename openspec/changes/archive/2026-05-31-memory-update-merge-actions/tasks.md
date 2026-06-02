## 0. 前置确认

- [x] 0.1 确认本 change 不修改 public API，不新增表结构
- [x] 0.2 确认不做 extraction quality evaluation、不接真实 embedding、不做 reflection 自动维护
- [x] 0.3 确认测试使用 tmp SQLite DB，不触碰 `data/`

## 1. Memory snapshot 输入

- [x] 1.1 Write failing tests: `extract_and_update()` 调用 LLM 时包含当前用户已有 memory snapshot
- [x] 1.2 Write failing tests: snapshot 限额为 identity 20、preferences 30、context 20，且 context 只包含未过期条目
- [x] 1.3 实现内部 snapshot 查询和 prompt 输入格式
- [x] 1.4 运行 `uv run pytest tests/unit -x -q`，确认 1.1/1.2 红测转绿

## 2. Update action

- [x] 2.1 Write failing tests: LLM 返回 `update` + 合法 `target_id` 时更新该 memory 的 content / updated_at
- [x] 2.2 Write failing tests: context memory 被 update 时刷新 30 天 TTL，identity / preferences 仍不过期
- [x] 2.3 Write failing tests: update 后调用 `vector_store.upsert(target_id, new_content, memory_namespace(user_id))`
- [x] 2.4 实现 update action 处理
- [x] 2.5 运行 `uv run pytest tests/unit -x -q`，确认 2.1-2.3 红测转绿

## 3. Delete action

- [x] 3.1 Write failing tests: LLM 返回 `delete` + 合法 `target_id` 时删除该 memory
- [x] 3.2 Write failing tests: delete 后调用 `vector_store.delete(target_id, memory_namespace(user_id))`
- [x] 3.3 Write failing tests: 非当前用户或不在 snapshot 中的 `target_id` 被忽略
- [x] 3.4 实现 delete action 处理
- [x] 3.5 运行 `uv run pytest tests/unit -x -q`，确认 3.1-3.3 红测转绿

## 4. Action contract 与冲突策略

- [x] 4.1 Write failing tests: `ignore` 不写入、不更新、不删除
- [x] 4.2 Write failing tests: 未知 action、缺失 `target_id`、非法 type、空 content 被忽略
- [x] 4.3 Write failing tests: identity/context 冲突场景下 mock LLM 返回 update 时不产生重复 memory
- [x] 4.4 Write failing tests: 一次性 preferences 请求 mock LLM 返回 ignore 时不产生 memory
- [x] 4.5 更新 extraction system prompt，明确 create / update / delete / ignore contract 和偏好判断规则
- [x] 4.6 运行 `uv run pytest tests/unit -x -q`，确认 4.1-4.4 红测转绿

## 5. 收尾验证

- [x] 5.1 运行 `uv run pytest tests/unit -x -q`
- [x] 5.2 运行 `uv run pytest -x -q`
- [x] 5.3 运行 `uv run ruff format src tests`
- [x] 5.4 运行 `uv run ruff check src tests`
- [x] 5.5 运行 `uv run mypy src`
- [x] 5.6 运行 `openspec validate memory-update-merge-actions`
