## 1. Slack 适配器传 loading_messages

- [x] 1.1 Write failing test: assistant `progress_func` 收到批级事件时,`set_status` 以 `loading_messages` 传当前批每个工具的可读文案(mock set_status,断言 kwargs 含 loading_messages 且覆盖全部工具)
- [x] 1.2 Implement: 新增 names→逐工具文案列表的辅助,`_route_assistant_message` 的 progress_func 调 `set_status(status, loading_messages=[...])`
- [x] 1.3 Write failing test: 初始 `set_status("🤔 思考中...")` 同时传 `loading_messages=["🤔 思考中..."]`
- [x] 1.4 Implement/verify 初始 loading_messages 通过 1.3
- [x] 1.5 Write failing/verify test: loading_messages 不含工具参数/敏感信息;set_status 异常仍被吞(降级不变)

## 2. 收尾验证

- [x] 2.1 受影响层:`uv run pytest tests/unit/test_slack_assistant.py tests/unit/test_slack_status.py tests/unit/test_im_progress_feedback.py -q`(无新增失败)
- [x] 2.2 改动文件 `uv run ruff format` + `ruff check` + `uv run mypy src/fleetent/im_gateway/slack.py`
- [x] 2.3 架构校验:im_gateway 未 import platform.*;agent 可脱离 platform 独立运行
- [x] 2.4 PR 门禁:`make test-pr` 全绿(除预存在 path 失败);integration 相关子集无新增失败
