## 1. P1 — 错误分类：LLM 超时归类（agent-error-classification）

- [x] 1.1 写测试（见红）：`tests/unit/test_error_classifier.py` 断言 `classify(httpx.ReadTimeout(...))` / `httpx.TimeoutException` / `openai.APITimeoutError` / `openai.APIConnectionError` 返回分类码 `llm_timeout`，且其标志位 `should_retry=True, should_switch_model=True, should_compress=False`；并断言这些异常不再返回 `unknown`
- [x] 1.2 实现：`runtime/error_classifier.py` 在 `ErrorCategory` 增加 `llm_timeout`，`_categorize` 识别 `httpx.ReadTimeout/TimeoutException` 与 `openai.APITimeoutError/APIConnectionError`，`CLASSIFICATION_TABLE` 挂 `should_retry=True, should_switch_model=True`（见绿）
- [x] 1.3 写测试（见红）：`tests/unit/` 断言 `_stream_policy_chat`/`_call_with_overflow_retry` 在首 target 抛 LLM 超时时，依标志位走重试（`model-transient-retry`）并在有备用 target 时切换（`model-fallback`），无备用时回原 target 重试
- [x] 1.4 验证 1.3 见绿（仅靠分类改动生效，不改主循环判定逻辑）

## 2. P2 — LLM client 显式超时与重试（llm-client-timeout）

- [x] 2.1 写测试（见红）：`tests/unit/` 断言 `runtime/loop._build_async_client(...)` 返回的 `AsyncOpenAI` 配置了显式 `timeout`（有限 read）与 `max_retries`（>0）；并断言超时阈值来自模块内可注入常量（可 monkeypatch）
- [x] 2.2 实现：`runtime/loop.py` 定义可注入超时常量（connect=5/read=90/write=10/pool=5）与 `_LLM_MAX_RETRIES=2`，`_build_async_client` 传入 `timeout=httpx.Timeout(...)` 与 `max_retries=...`（见绿）

## 3. P0 — IM 运行失败兜底回帖 + 清 loading（im-run-failure-fallback）

- [x] 3.1 写测试（见红）：integration/unit 断言 `im_gateway/normalizer.route` 主路径在 `agent_loop.run` 抛异常时调用 `msg.reply_func` 一次且文案非空（兜底提示）
- [x] 3.2 写测试（见红）：断言兜底路径触发后异常**不再向上抛出**（route 正常返回），且产生一条含异常类型的 error 日志（不吞异常）
- [x] 3.3 写测试（见红）：断言失败轮仍调用 `session_mgr.save`（用户输入不丢）；并断言「正常成功返回」时不触发兜底（不回多余提示）
- [x] 3.4 写测试（见红）：断言兜底经 `reply_func` 完成 loading 状态清除——以 mock reply_func 验证其被调用（清状态逻辑内置于 reply_func），或在 slack 适配层测试 `reply_func` 调用即触发 `setStatus("")`
- [x] 3.5 实现：`im_gateway/normalizer.py` 在 `register_run` 内将 `agent_loop.run(...)` 包入 try/except：异常时 `logger.error(...)` + `with suppress(Exception): await msg.reply_func("⚠️ 处理时出错或超时了，请重试。")` + `await session_mgr.save(...)` + `return`（不 raise）（见绿 3.1–3.4）
- [x] 3.6 写测试（见红）：`im-progress-feedback` 失败路径清状态——在 slack 适配层断言「失败兜底经 `reply_func` 投递时同样先调用 `set_status("")`」（与现有"完成后清状态"对称）
- [x] 3.7 验证 3.6 见绿：确认 `reply_func` 在失败兜底与正常完成两条路径上都触发状态清除（无需改 `_make_status_funcs`，行为由 reply_func 既有清状态逻辑覆盖；若 mock 验证不足则补适配层用例）

## 4. 收尾验证

- [x] 4.1 跑受影响层窄命令全绿（`uv run pytest tests/unit/test_error_classifier.py tests/unit/<loop/client test> tests/integration/<normalizer test> -q`）
- [x] 4.2 验证基线：在无 platform、platform 表不存在环境下 `fleetent agent run` 仍可完成一次对话（P0/P1/P2 均不触 platform）
- [x] 4.3 `make test-pr` + `make test-integration-ci` 收尾全绿（无新增失败）
- [x] 4.4 模块边界：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过；确认 `im_gateway`/`runtime` 未新增 `import fleetent.platform.*`
