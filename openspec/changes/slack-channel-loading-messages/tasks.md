## 1. 频道 fallback 路径补 loading_messages

- [ ] 1.1 Write failing test: `_make_status_funcs` 的 progress 调用以 `loading_messages` 传当前批逐工具文案(mock client.assistant_threads_setStatus,断言 kwargs 含 loading_messages)
- [ ] 1.2 Write failing test: `_make_status_funcs` 初始 setStatus 传 `loading_messages=["🤔 思考中..."]`
- [ ] 1.3 Implement: `_make_status_funcs` 两处 setStatus 增传 loading_messages(复用 `_loading_messages_for_event`)
- [ ] 1.4 Verify 1.1/1.2 转绿;既有降级/清除测试仍绿

## 2. 收尾验证

- [ ] 2.1 `uv run pytest tests/unit/test_slack_status.py tests/unit/test_slack_assistant.py -q`(无新增失败)
- [ ] 2.2 改动文件 ruff format/check + `mypy src/fleetent/im_gateway/slack.py`
- [ ] 2.3 架构:im_gateway 不依赖 platform
- [ ] 2.4 `make test-pr` 全绿(除预存在 path 失败)
