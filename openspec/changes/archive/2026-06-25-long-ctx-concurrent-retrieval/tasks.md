## 1. 配置项

- [x] 1.1 写测试：`LongTermContextSettings` 含 `retrieval_timeout_seconds`，默认 5.0、可被配置覆盖（unit，先见红）
- [x] 1.2 实现：在 `LongTermContextSettings` 加 `retrieval_timeout_seconds: float = 5.0`，`_ltc_config()` 暴露（见绿）

## 2. 单路超时降级 helper

- [x] 2.1 写测试：单路 helper 在协程正常返回时透传结果、记一条带耗时的日志（unit，先见红）
- [x] 2.2 写测试：单路 helper 在 `wait_for` 超时时返回空结果、记 warning、不抛异常（unit，先见红）
- [x] 2.3 写测试：单路 helper 在协程抛非超时异常时返回空结果、记 warning（含异常类型）、不抛异常（unit，先见红）
- [x] 2.4 实现：新增 `_retrieve_with_timeout(name, coro_factory, timeout)` helper——`time.monotonic()` 计时 + `asyncio.wait_for` + 超时/异常降级为空 + 结构化日志（见绿）

## 3. build_context 三路并发

- [x] 3.1 写测试：三路检索并发执行——人为给每路加延迟 D，断言总耗时约 D 而非 3×D（unit，先见红）
- [x] 3.2 写测试：单路（memory）超时降级时，knowledge 与 agent_memory 结果仍正常并入，`build_context` 不抛异常（unit，先见红）
- [x] 3.3 写测试：三路全超时返回空 `BuiltContext`（text/sources 均空），与"三路均无结果"一致（unit，先见红）
- [x] 3.4 写测试：`agent_memory` backend 未接线（RuntimeError）经统一 helper 降级为空，行为与现状一致（unit，先见红）
- [x] 3.5 实现：将 `build_context` 三路顺序 `await` 改为 `asyncio.gather(return_exceptions=True)`，每路经 `_retrieve_with_timeout` 包裹；合并/排序/预算逻辑不变（见绿）

## 4. 收尾

- [x] 4.1 回归：`uv run pytest tests/unit/test_long_term_context_budget_policy.py tests/integration/test_long_term_context_runtime.py tests/integration/test_long_term_ctx.py -q`，对照 main 无新增失败
- [x] 4.2 `make test-pr` 全绿（changed-file ruff + 层边界 + unit）
- [x] 4.3 边界自检：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过，确认 `long_term_ctx` 未新增 platform import
