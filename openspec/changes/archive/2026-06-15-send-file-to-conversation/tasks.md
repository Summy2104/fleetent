## 1. ToolContext 携带对话地址

- [x] 1.1 写测试（红）：`tests/unit/test_tool_registry.py` 断言 `ToolContext` 可接受 `conversation_address` 字段、默认 `None`
- [x] 1.2 实现（绿）：`tools/registry.py` `ToolContext` 新增 `conversation_address: Any = None`

## 2. send_file 投递回当前对话

- [x] 2.1 写测试（红）：`send_file` 行为单测——`conversation_address` 为频道（`target_type="channel"`、`chat_id`、`thread_id`）时，`outbound.send_file_to` 以 `target=chat_id`/`target_type="channel"`/`thread=thread_id` 调用（mock 断言）
- [x] 2.2 写测试（红）：`conversation_address` 为 DM（`target_type="user"`）时，按 DM 地址投递
- [x] 2.3 写测试（红）：无 `conversation_address`、`session_context` 非空时，回退按 `sender_id`/`target_type="user"` 投递（旧行为）
- [x] 2.4 写测试（红）：`session_context is None` 时仍 fail-closed（无会话发起人说明文本，不发送）——回归保护
- [x] 2.5 实现（绿）：`tools/builtin_tools.py` `send_file` 用 `tool_context.conversation_address` 解析 `target`/`target_type`/`thread`，缺失回退 `sender_id` DM；透传给 `outbound.send_file_to`；结果文本回显实际收件人

## 3. loop 接线注入对话地址

- [x] 3.1 实现（绿）：`runtime/loop.py` IM 网关 run 路径的 `ToolContext` 构建点注入 `conversation_address=conversation_address`
- [x] 3.2 验证：流式路径（`run_stream`）不注入（无入参、无 outbound），保持现状

## 4. 收尾验证

- [x] 4.1 跑受影响层单测全绿（`tests/unit/test_tool_registry.py` + send_file 单测）
- [x] 4.2 `make test-pr` 全绿（无新增失败）
- [x] 4.3 `uv run pytest tests/integration -q` 对照 main 基线无新增失败
- [x] 4.4 `openspec validate send-file-to-conversation --strict` 通过
- [x] 4.5 `uv run mypy src` 无新增错误；改动文件 ruff 净
