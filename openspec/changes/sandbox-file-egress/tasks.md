## 1. 统一出站文件原语（outbound.send_file_to + Telegram send_document）

- [x] 1.1 写 unit 测试：`outbound.send_file_to(platform, connector, target, path, ...)` 按 `platform` 分派 —— Slack 走 `files_upload_v2`、Telegram 走 `send_document`；底层连接器抛错时返回 False 且不抛；未知 platform 返回 False（mock 连接器，先见红）
- [x] 1.2 在 `fleetent/outbound.py` 真实模块实现 `send_file_to`：对齐 `send_to` 的按 platform 分派结构，Slack `files_upload_v2(channel, thread_ts, file)`、Telegram `bot.send_document(chat_id, document)`，失败记 warning 返回 False 不抛；由 `im_gateway/outbound.py` shim re-export（见绿）
- [x] 1.3 写 integration 测试：经 mock Slack 连接器与 mock Telegram bot 各投递一个本地文件，断言调用了正确的底层方法与参数（channel/thread/file 对 Slack，chat_id/document 对 Telegram）

## 2. send_file 工具（收件人固定 + 路径翻译 + fail-closed）

- [x] 2.1 写 unit 测试：`send_file(path)` 在 `session_context` 非空 + `chat_type=dm` + `workspace_scope=session` 时，按 `session_context.platform`/`sender_id` 经统一原语发送，结果回显**实际收件人**；收件人不取任何模型参数（mock manager.scope=session、mock 连接器，先见红）
- [x] 2.2 写 unit 测试：路径翻译 —— 相对路径经 `workspace_host_path()` + `resolve_host_path()` 解析为宿主真实文件；`..` 越界路径被拒、返回说明文本不发送（先见红）
- [x] 2.3 写 unit 测试：fail-closed 矩阵 —— `chat_type=channel` / `workspace_scope=agent` / `session_context=None` 各不发送且返回引导改用 `send_im_message` 或"无会话发起人"的说明文本（先见红）
- [x] 2.4 写 unit 测试：降级 —— 无连接器（`outbound_connectors` 空）/ 目标平台不支持出站文件 / 文件不存在 / 投递失败 各返回说明文本且不抛（先见红）
- [x] 2.5 在 `tools/builtin_tools.py` 实现 `send_file`（`@tool` 注册 `risk_level="none"`，LLM schema 仅 `path` 参数，`tool_context` out-of-band）：读 `tool_context.session_context` 固定收件人、读 `_get_manager().scope` 判 workspace_scope、经 `workspace_host_path()` + `file_sandbox_io.resolve_host_path()` 翻译读字节、经 `outbound.send_file_to` 发送；免审批前置三条 + 全部降级分支 fail-closed（见绿）
- [x] 2.6 跑通 2.1–2.4 全绿；确认未改 `resolve_action_mode` 契约、未改 registry 既有 risk 常量、未新增 action gate 动态 risk 缝

## 3. 废弃正则嗅探回流（normalizer 显式外发失败）

- [x] 3.1 写 unit 测试：`route()` 完成后，对含**容器内路径**（如 `/workspace/out.png`）的本轮 tool 结果 MUST NOT 用宿主 `Path.is_file()` 判存在后自动上传（断言不调用 upload 路径）（先见红）
- [x] 3.2 写 unit 测试：本轮确有生成型工具产物却无法宿主命中时，`route()` 追加显式"外发失败：请用 send_file 发送"提示（断言提示出现），MUST NOT 静默跳过（先见红）
- [x] 3.3 在 `im_gateway/normalizer.py` 移除 `route()` 末尾(615-620)基于 `_extract_generated_image_paths` + 宿主 `Path.is_file()` 的自动上传；改为"本轮有产物意图却宿主命不中 → 显式外发失败提示"；`_extract_generated_image_paths`/`_IMAGE_GENERATED_RE`/`_FILE_WRITTEN_RE` 按是否仍需驱动提示决定退役或降级（见绿）
- [x] 3.4 跑通 3.1–3.2 全绿；确认 `NormalizedMessage.upload_func` 注入通道仍保留（供出站文件原语复用、契约不变）

## 4. Slack/Telegram 适配器收敛与出站文件投递

- [x] 4.1 写 integration 测试：`slack.py` 的出站文件上传经统一 `outbound.send_file_to` 原语投递（行为与收敛前一致：同 `files_upload_v2` 调用、单文件失败优雅降级）（先见红/对照）
- [x] 4.2 将 `slack.py:_make_upload_func` 收敛到 `outbound.send_file_to` 之上（去重，行为不变）（见绿）
- [x] 4.3 写 integration 测试：Telegram DM 会话经 `send_file` → 统一原语 → `bot.send_document` 投递 workspace 产物（mock bot，先见红）
- [x] 4.4 在 `im_gateway/telegram.py` 接通 Telegram 出站文件投递路径（经统一原语），跑通 4.3

## 5. 边界与收尾

- [x] 5.1 跑 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 无新增跨包 internal import；确认 `tools`/`outbound`/`im_gateway` 均未 `import fleetent.platform.*`
- [x] 5.2 冒烟：agent 在无 platform、platform 表不存在环境下 `fleetent agent run` 仍可完成一轮对话；`send_file` 在该 CLI 路径（无 IM 连接器）返回说明文本不抛
- [x] 5.3 `uv run ruff format src tests` + `uv run ruff check src tests` 改动文件、`uv run mypy src` 通过
- [x] 5.4 `make test-pr` 全绿（对照 main 基线无新增失败）+ `uv run pytest tests/integration -q` 无新增失败
- [x] 5.5 `openspec validate sandbox-file-egress --strict` 通过
