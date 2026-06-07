## 1. 流式透出 reasoning_delta（TDD）

- [x] 1.1 写失败测试（`tests/unit/test_agent_loop.py`，复用 mock_client + 自定义带 reasoning_content 的流）：`run_stream` 在 chunk delta 带字符串 `reasoning_content` 时产出 `reasoning_delta` 事件、其文本不入最终回复；现有流式测试（MagicMock delta）不产出 reasoning_delta（行为不变）。看红
- [x] 1.2 实现：`run_stream` chunk 循环加防御式 `reasoning_content`(isinstance str) → yield `reasoning_delta`（不入 reply_parts/messages）；更新事件类型 docstring。看绿

## 2. 文档 + 收尾

- [x] 2.1 `agents/default/agent.yaml.example` 注明用 `target.params` 的 `reasoning_effort`/`extra_body.reasoning` 开启请求侧 reasoning。
- [x] 2.2 `uv run ruff format`（改动）、`ruff check`（改动）、`mypy src/fleetent/runtime/loop.py`、全量 `uv run pytest -x -q`；`openspec validate agent-reasoning-passthrough --strict`。
