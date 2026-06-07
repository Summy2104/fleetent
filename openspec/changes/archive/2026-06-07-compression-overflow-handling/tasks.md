## 1. run() 反应式溢出恢复（TDD）

- [x] 1.1 写失败测试（`tests/unit`，patch `_call_policy_chat` 首次抛 context_overflow 错、二次成功；patch `compress_for_context_overflow` 返回更短序列）：`run()` 不崩溃、压缩后重试成功、消息被原地压缩；非溢出错误仍传播。看红
- [x] 1.2 实现 `_call_with_overflow_retry`（消费 `classify().should_compress`，原地压缩重试，cap + 无进展守卫）+ run() 改用之；loop.py 增 import。看绿

## 2. 守卫 + run_stream（TDD）

- [x] 2.1 写失败测试（`tests/unit`）：压缩无进展（token 未降）时放弃 re-raise（run）；`run_stream` 溢出时压缩重试成功产出 done、恢复失败 emit error。看红
- [x] 2.2 实现 run_stream 内联溢出重试 + 无进展守卫。看绿

## 3. 收尾

- [x] 3.1 `uv run ruff format`（改动文件）、`ruff check`（改动）、`mypy src/fleetent/runtime/loop.py`、全量 `uv run pytest -x -q`
- [x] 3.2 `openspec validate compression-overflow-handling --strict` 通过
