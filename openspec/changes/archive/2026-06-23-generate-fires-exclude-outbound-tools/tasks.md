## 1. loop.run 收口外发工具

- [x] 1.1 写测试(unit):`_filter_outbound_tools(schemas, suppress=True)` 移除 `send_im_message`/`send_file`,保留其他;`suppress=False` 原样返回 —— 见红
- [x] 1.2 实现:`loop` 加 `_OUTBOUND_DELIVERY_TOOLS` 常量 + `_filter_outbound_tools` helper;`run()` 加 `suppress_outbound_tools: bool=False`,在 schema 过滤链应用 —— 见绿

## 2. cron generate/action 透传

- [x] 2.1 写测试(unit):`_fire` 对 generate 任务调 `agent_loop.run` 时传 `suppress_outbound_tools=True`;对 action 任务传 `False` —— 见红
- [x] 2.2 实现:`_agent_run` 加 `suppress_outbound: bool=False` 透传给 `run`;`_fire` 调用处传 `suppress_outbound=(task_type=="generate")` —— 见绿

## 3. 收尾门禁

- [x] 3.1 跑 `tests/unit/test_cron_fire_outbound_connectors.py` 等既有 cron 用例确认无回归
- [x] 3.2 `make test-pr` 全绿;改动文件 `ruff check` 干净
