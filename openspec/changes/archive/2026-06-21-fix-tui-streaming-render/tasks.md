> 说明:本修复在排障过程中已实现并经 CPR 精确 harness + 人工终端验证;以下任务记录已完成的工作(全部 `[x]`),归档前按"何时跑什么"复跑门禁。

## 1. 完整行流式 emit(TDD)

- [x] 1.1 写测试:`text_delta` 无换行时**不**立即 emit、缓冲;`done` 时按完整行 flush(`tests/unit/test_tui_app.py::test_on_event_buffers_partial_text_and_flushes_on_done`)
- [x] 1.2 写测试:`text_delta` 含换行时整行立即 emit、保留尾部半行(`test_on_event_emits_complete_lines_immediately`)
- [x] 1.3 实现:`AppController` 加 `_text_buf` + `_flush_complete_lines`/`_flush_text`;`on_event` 累积 text、其他事件先 flush 再渲染
- [x] 1.4 实现:`_default_emit` 在 prompt 运行时经 `run_in_terminal` 输出,否则直接 print

## 2. 去多余空行(TDD)

- [x] 2.1 写测试:连续结构化事件 / 文本后接结构化事件,emit 序列无 `\n\n`、无前导 `\n`(`test_on_event_no_blank_lines_around_structured_events`)
- [x] 2.2 写测试:`render.format_event` 结构化事件无前导 `\n`、`done` 返回 `None`(`tests/unit/test_tui_render.py`)
- [x] 2.3 实现:`render.py` 去掉 tool_call/tool_result/error/approval 前导 `\n`;`done` 返回 `None`

## 3. 收尾

- [x] 3.1 模块边界:owning=`tui`,无表/迁移/协议变更;不 import platform
- [x] 3.2 文档:`app.py`/`render.py` docstring 同步新渲染机制
- [x] 3.3 门禁:`make test-pr` + `make test-unit-ci`(覆盖率)对照 main 基线无新增失败(归档前复跑)
