## 1. 结果规范化核心逻辑（TDD）

- [x] 1.1 Write failing tests for the shared result normalizer (`_normalize_tool_result` + `_block_to_text`) in `tests/unit/` covering: 多文本块按序聚合；单文本块保持不变；image-first 块返回含 mimeType 的 marker 且不抛；embedded resource 带文本内联；image base64 不进入返回文本；`isError` 标记错误且含错误文本、不抛；`isError` 假/缺省时不标错误；仅 `structuredContent` 时序列化为含字段的 JSON；内容块存在时优先于 structuredContent。运行 `uv run pytest -x -q` 看到红。
- [x] 1.2 Implement `_block_to_text(block)`（duck-typing 兼容 SDK 对象与 dict）与 `_normalize_tool_result(content_blocks, *, structured_content, is_error)` 使 1.1 全绿。

## 2. stdio / http 调用路径接线（TDD）

- [x] 2.1 Write failing tests for `_call_stdio_tool`（mock `ClientSession.call_tool` 返回多块/图片/`isError` 的构造 result）与 `_call_http_tool`（mock httpx 返回构造的 JSON-RPC `result`，含 `content`/`structuredContent`/`isError`），断言两条路径经由规范化函数产出预期文本、stdio 图片结果不再崩溃。运行 `uv run pytest -x -q` 看到红。
- [x] 2.2 改造 `_call_stdio_tool` 与 `_call_http_tool`：收集完整 `content` 列表 + `structuredContent` + `isError` 并调用 `_normalize_tool_result`，保留既有降级/认证短路逻辑不变，使 2.1 全绿。

## 3. 文档与收尾

- [x] 3.1 修正 `docs/capabilities/mcp.md`「现状」节：把已实现的 streamable HTTP / OAuth2 / 健康重连 / 会话连续性 / 降级策略由「⚡部分/规划中」改为如实状态；补充工具结果处理（多块/非文本/isError/structuredContent）的现状。
- [x] 3.2 新建 `docs/records/mcp-enhancement-2026-06/gap-analysis.md`（四参考项目 MCP 机制差距分析，作为 6 变更程序依据）与 `decision-log.md`（开篇记录本变更 mcp-result-fidelity 的问题与决策、改进点）。
- [x] 3.3 收尾全量校验：`uv run pytest -x -q`、`uv run ruff format src tests && uv run ruff check src tests`、`uv run mypy src`、`uv run python scripts/check_test_layers.py` 全部通过。
