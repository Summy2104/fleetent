## 1. 前置核实（实现前的事实确认，无代码改动）

- [ ] 1.1 核实 OpenAI 兼容 chat API 的 `content` 内容块数组格式（`text` 块 / `image_url` 块 + `data:` URL），确认 SDK 透传无需额外转换
- [ ] 1.2 核实 `context_mgr.estimate_tokens`（行 20-22 `len(str(m))`）与 `eval_logger._serialize`（行 87-92）对 dict content 的现有处理，定占位计量/序列化接入点
- [ ] 1.3 核实 `run()` 的 `user_input` 提取（agent_loop.py 行 258-261）与 `extract_and_save`，确认 content 为数组时取文本块的降级策略
- [ ] 1.4 核实 model_router 的 task_type 配置机制：`get_async_client_and_config` 如何按 task_type 选 provider、如何新增 `vision` task_type、以及 task_type 未配置时的现状行为（决定「无 vision 路由」如何检测并报错）

## 2. 构造辅助与判定（multimodal.py）

- [ ] 2.1 Write failing tests for `is_multimodal_content()`：content 为 list → True；为 str → False。`tests/test_multimodal.py`。看到红
- [ ] 2.2 Implement `is_multimodal_content()`，看到绿
- [ ] 2.3 Write failing tests for `build_image_block()`：输入图片字节 + mime → 返回 `{"type": "image_url", "image_url": {"url": "data:{mime};base64,..."}}`，base64 用标准库解码可还原原字节。看到红
- [ ] 2.4 Implement `build_image_block()`，看到绿
- [ ] 2.5 Write failing tests for `build_message_with_images()`：文本 + 多张图片 → user 消息含 1 个 text 块 + N 个 image_url 块；无文本时仅图片块。看到红
- [ ] 2.6 Implement `build_message_with_images()`，看到绿
- [ ] 2.7 Write failing tests：非图片二进制 mime → 归一化为文本占位块（不产出 image_url）。看到红
- [ ] 2.8 Implement 非图片归一化为占位，看到绿
- [ ] 2.9 Write failing tests for `has_image_block()`：messages 含 image_url 块 → True；仅文本块数组或纯 str content → False。看到红
- [ ] 2.10 Implement `has_image_block()`，看到绿

## 3. 压缩对图片块占位计量（context_mgr.py）

- [ ] 3.1 Write failing tests：含大体积 base64 图片块的消息进入 `estimate_tokens`，图片块按固定占位计量，估算不因 base64 长度误超阈值；纯文本估算不变。`tests/test_context_mgr.py`。看到红
- [ ] 3.2 Implement `estimate_tokens` 对图片内容块占位计量，看到绿

## 4. trace 对图片块占位序列化（eval_logger.py）

- [ ] 4.1 Write failing tests：含图片块的 messages 经 `_serialize` 后，图片块替换为占位（含 mime + 字节数），不含完整 base64 串。看到红
- [ ] 4.2 Implement `_serialize` 图片块占位，看到绿

## 5. 接入 run()

- [ ] 5.1 Write failing tests：`run()` 收到含图片内容块的消息，内容块原样透传给 LLM（断言 mock `_call_with_fallback` 收到的 messages 含图片块）；`user_input` 提取在 content 为数组时取文本块。mock `get_async_client_and_config`。看到红
- [ ] 5.2 Implement：放宽 `messages` content 类型；`user_input` 提取兼容数组取文本块；透传不解释内容块。看到绿
- [ ] 5.3 Write failing test 守卫：`content` 为 str 的纯文本调用行为与现状一致（回归守卫）。看到红（若已绿说明守卫无效，调整断言）
- [ ] 5.4 Write failing tests for 视觉路由：`run()` 收到含图片块消息 → 调用 `get_async_client_and_config("vision")`（断言 task_type 实参）；纯文本 → `"default"`；含图片但 vision 未配置 → 抛明确错误且不发起 LLM 调用。看到红
- [ ] 5.5 Implement：`run()` 依 `has_image_block` 选 task_type（vision / default），无 vision 路由时报错（方案 A）。看到绿

## 6. 接入 run_stream()

- [ ] 6.1 Write failing tests：`run_stream()` 支持图片输入（经构造辅助或预构造 messages）并透传 LLM；纯文本 `user_input` 路径不变。mock `get_async_client_and_config`。看到红
- [ ] 6.2 Implement `run_stream()` 图片输入透传，看到绿
- [ ] 6.3 Write failing tests：`run_stream()` 含图片 → vision 路由；未配置 vision → 报错。看到红
- [ ] 6.4 Implement `run_stream()` 视觉路由（同 run() 逻辑），看到绿

## 7. 收尾

- [ ] 7.1 全量 `uv run pytest`（带 `ANTHROPIC_API_KEY`），无回归
- [ ] 7.2 `uv run ruff format src tests && uv run ruff check src tests` 全绿
- [ ] 7.3 `uv run mypy src` 无新增错误模式
