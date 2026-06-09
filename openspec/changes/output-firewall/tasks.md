## 1. 输出防火墙：run() 路径（_backfill_slots）

- [ ] 1.1 Write failing unit tests `tests/unit/test_loop_output_firewall.py`：含密钥的工具结果（如 `sk-ant-...`、`API_KEY=xxx`、`Authorization: Bearer xxx`）经 `_backfill_slots` 后进入 messages 的内容已被 `[REDACTED]`；不含密钥的结果原样保留；placeholder slot 内容不被脱敏改写；脱敏发生在截断之前（构造跨边界密钥，断言被掩码）（tests/unit）
- [ ] 1.2 Implement：`_backfill_slots` 在 post_tool_use hook 之后、`truncate_tool_result` 之前对非 placeholder content 调 `redact_secrets`，pass unit tests

## 2. 输出防火墙：run_stream 路径

- [ ] 2.1 Write failing unit tests：run_stream 的工具结果同样在进入 messages/事件前被脱敏（mock LLM 产一个返回密钥的工具调用，断言流出的 tool 结果已 `[REDACTED]`）（tests/unit）
- [ ] 2.2 Implement：run_stream 内联 backfill 同样插入 `redact_secrets`（与 _backfill_slots 同语义），pass unit tests

## 3. 收尾验证

- [ ] 3.1 解耦验证：改动零 platform import；模块依赖护栏测试通过；无 platform DB 环境下脱敏生效（纯文本变换，无 DB 依赖）
- [ ] 3.2 全量收尾：`make test-pr` 全绿（run_code 既有脱敏测试不回归）＋ ruff format/check + mypy 改动文件 + integration 对照 main 基线无新增失败
