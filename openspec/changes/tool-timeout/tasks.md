## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 `_safe_dispatch`（`agent_loop.py` 行 185-214）是工具执行唯一边界：调用 `dispatch`、`await` coroutine、把异常归一为 `(error_text, failed=True)`；确认超时竞速与 token 注入应叠加于此处
- [ ] 1.2 核实 AR19 `cancellation.py` 的 `CancelToken(deadline=...)` 契约：`is_cancelled()` 合并显式 `cancel()` 与 `time.monotonic() >= deadline`；`dispatch` 仅向声明 `cancel_token` 参数的工具注入（out-of-band，不进 schema）。确认「超时 = `CancelToken(deadline=now+timeout)`」复用方式
- [ ] 1.3 核实 AR5 `error_classifier.py`：`ErrorCategory.tool_timeout` 与 `CLASSIFICATION_TABLE[tool_timeout]`（三标志 False）已存在；`_categorize` 现仅识别 `APIStatusError`，`tool_timeout` 为预留码不可达；确认接入点（D2-a 扩展 `_categorize` 识别 `TimeoutError` / D2-b 工具层直接读表，参照 `mcp_client._disconnect_classification`）
- [ ] 1.4 核实 `tool_registry.py` 的平行元数据范式：`_risk_levels` / `_connectors` 与 `_OUT_OF_BAND_PARAMS`、`_build_schema` 排除规则；确认 `timeout` 元数据沿用「平行表 + 不进 schema」

## 2. per-tool 超时元数据（tool_registry.py）

- [ ] 2.1 Write failing tests for `@tool(timeout=...)` 记录与查询：`@tool(timeout=5)` 后 `get_timeout(name)` 返回 5；未声明的工具 `get_timeout` 返回 None；超时元数据不出现在 `get_schemas()` 导出的 schema 中。运行 `uv run pytest -x -q` 看到红
- [ ] 2.2 Implement `@tool(timeout=...)` 参数、平行元数据表与 `get_timeout(name)`，确保不进 `_build_schema`，看到绿

## 3. 有效超时解析与全局默认（可注入）

- [ ] 3.1 Write failing tests for 有效超时解析：声明 per-tool 时限用之、未声明用全局默认（默认 30s）；monkeypatch 全局默认常量后未声明工具按注入值计算。看到红
- [ ] 3.2 Implement 全局默认 `DEFAULT_TOOL_TIMEOUT`（模块级常量，可 monkeypatch）与有效超时解析（per-tool 覆盖全局），看到绿

## 4. 超时竞速 + cancel token 注入（agent_loop._safe_dispatch）

- [ ] 4.1 Write failing tests for 超时竞速：注入极短超时（如 0.01s）+ 可控慢工具 stub（`asyncio.Event` / 受控 sleep，不真实长 sleep），断言 `_safe_dispatch` 在时限内停止等待、返回 `failed=True`，未超时工具正常返回（行为不变）。看到红
- [ ] 4.2 Implement 在 `_safe_dispatch` 解析有效超时、构造 `child = CancelToken(deadline=now+t, parent=run_cancel_token)` 注入声明接受 token 的工具（经 `parent` 链接合并 run 级取消，复用 AR20 补全的 `parent` 原语，不顶掉/旁路 run 级 token）、在 await 层竞速（`asyncio.wait_for` 或等价），看到绿
- [ ] 4.3 Write failing tests for token 取消：超时到达时该次执行的 cancel token 被 `cancel()`（声明接受 token 的慢工具能观察到 `is_cancelled()` 为真）。看到红
- [ ] 4.4 Implement 超时分支 `cancel()` token，看到绿
- [ ] 4.5 Write failing tests for run 级取消经 `parent` 传播：构造 run 级 cancel token 透传 `_safe_dispatch`，在工具自身 deadline 到达前 `cancel()` run 级 token，断言该工具的 per-tool token 经 `parent` 链接 `is_cancelled()` 也为真（声明接受 token 的慢工具观察到取消并停止）。看到红
- [ ] 4.6 Implement 经 `parent=run_cancel_token` 挂接 run 级 token，使工具同时响应自身超时与 run 级取消，看到绿

## 5. 超时归类为 tool_timeout（接入 AR5 预留码）

- [ ] 5.1 Write failing tests for 归类：超时失败的分类码为 `tool_timeout`（非 `tool_crash`/`unknown`），标志位与 `CLASSIFICATION_TABLE[tool_timeout]` 一致；返回的错误文本表明是超时。看到红
- [ ] 5.2 Implement 超时归一为 `tool_timeout`（按 D2 择一接入点），错误文本指明工具超时，看到绿

## 6. SB7 边界（不实现 docker kill）

- [ ] 6.1 Write failing test for 边界：工具层超时路径不触发任何 `docker kill` / 容器强制终止逻辑（用 mock 沙箱/工具断言无 kill 调用）；不协作工具超时时主循环仍停止等待并返回 `tool_timeout`。看到红
- [ ] 6.2 Implement 确认超时仅做 await 层停止等待 + cancel token，不调用 `docker kill`（明确划归 SB7），看到绿

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归；异步超时测试稳定（注入极短超时，不依赖墙钟长等待）
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿（行长 100）
- [ ] 7.3 `uv run mypy src` strict 无新增错误
