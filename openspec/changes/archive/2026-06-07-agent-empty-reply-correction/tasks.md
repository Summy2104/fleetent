## 1. 空回复自纠错（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_agent_loop.py`，复用 mock_client）：`run()` 首轮空回复→注入纠正重跑→第二轮非空→返回非空（create 调用 2 次）；持续空回复达上限后返回空、不无限循环；非空回复一次返回（不重跑）。`run_stream` 同理（空流→纠正重跑→非空）。看红
- [x] 1.2 实现：`run()` 与 `run_stream()` finish 分支加"空白回复 + 计数<上限 → 追加纠正 user 消息 + continue"；新增 `_MAX_EMPTY_REPLY_RETRIES` / `_EMPTY_REPLY_CORRECTION`。看绿

## 2. 收尾

- [x] 2.1 `uv run ruff format`（改动）、`ruff check`（改动）、`mypy src/fleetent/runtime/loop.py`、全量 `uv run pytest -x -q`；`openspec validate agent-empty-reply-correction --strict`。
