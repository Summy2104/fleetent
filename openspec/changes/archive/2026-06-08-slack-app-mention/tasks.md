## 1. 实现（im_gateway/slack.py）

- [ ] 1.1 写测试：`app_mention` handler 已注册，@mention 消息路由到 normalizer（unit）
- [ ] 1.2 写测试：`message` handler 仅在 `channel_type == "im"` 时路由（unit）
- [ ] 1.3 写测试：普通频道消息（非 @mention、非 DM）不路由（unit）
- [ ] 1.4 运行测试，确认全红
- [ ] 1.5 实现：提取 `_handle()` 内部函数，注册 `app_mention` 和 DM-only `message` 两个处理器
- [ ] 1.6 运行测试，确认全绿

## 2. 全量回归

- [ ] 2.1 运行 `uv run pytest -x -q`，确认全绿
