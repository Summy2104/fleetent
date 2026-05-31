## Why

主循环目前只处理纯文本消息：`run()` 接收 `messages: list[dict]`，`run_stream()` 接收 `user_input: str`，`content` 字段一律当作字符串。但企业场景里用户经常发图片（截图报错、单据、图表），IM 平台（Slack / Telegram）也支持图片附件。当前这些非文本内容无法透传给支持视觉的 LLM，只能丢弃或转述，损失信息。

OpenAI 兼容的 chat API 支持 `content` 为内容块数组（`[{"type": "text", ...}, {"type": "image_url", ...}]`），其中 `image_url` 可携带 base64 data URL。这是 AR21（多模态输入支持）：让平台能接收图片等非文本内容并透传 LLM，数据全程留在内网（base64 内联，不依赖外部图床）。

## What Changes

- **支持图片内容透传 LLM**：主循环接受 `content` 为内容块数组（文本块 + 图片块混合），原样透传给 `_call_with_fallback` / `_stream_with_fallback`，不再假设 `content` 必为字符串。
- **支持 base64 编码图片作为消息内容**：图片以 `image_url` 内容块承载，`url` 为 `data:image/...;base64,...` 形式，数据不出内网。
- **检测图片并路由到视觉模型**：主循环检测到消息含图片块（`has_image_block`）时，路由到 model_router 的 `vision` task_type（视觉模型），而非默认 chat 模型；若未配置 `vision` 路由，**明确报错**，不静默发给非视觉模型撞 400。
- 提供构造辅助（建议 `src/fleetent/multimodal.py`）：把（文本 + 图片字节/base64）组装为合法的内容块数组消息，供 IM / HTTP 入口复用。
- **纯文本路径完全向后兼容**：`content` 为 `str` 时行为与现状一致；只有传入内容块数组时才走多模态路径。
- 与既有模块的协调：上下文压缩（`context_mgr`）与消息卫生（若已合入）对含图片块的消息须不崩溃——图片块在 token 估算与序列化时按占位处理，不破坏 tool 配对与角色契约。
- **边界（明确不做）**：音频 / 视频暂不支持；输入若含非图片的二进制内容，归一化为文本占位提示，不透传。

## Capabilities

### New Capabilities
- `multimodal-input`: 多模态输入支持——主循环接受 `content` 为文本+图片内容块数组并透传 LLM；含图片时检测并路由到 `vision` task_type（视觉模型），未配置则明确报错；图片以 base64 data URL 内联（数据不出内网）；纯文本路径完全向后兼容；音频/视频不支持，非图片二进制归一化为文本占位。

### Modified Capabilities
<!-- 无既有 spec 的需求级行为变更。纯文本路径行为不变；多模态仅在 content 为内容块数组时启用。 -->

## Impact

- **代码**：
  - 新增 `src/fleetent/multimodal.py`（`build_image_block()` / `build_message_with_images()` 等构造辅助 + `is_multimodal_content()` 判定）。
  - 修改 `src/fleetent/agent_loop.py`：`run()` 的 `messages` 类型放宽以接受内容块数组；`run_stream()` 增加可选图片输入参数（或接受预构造 messages），透传不变；`user_input` 提取（行 258-261）兼容 content 为数组（取其中文本块）；含图片时 `get_async_client_and_config("vision")` 取代 `"default"`，未配置 vision 路由则报错。
  - 修改 `src/fleetent/model_router.py` / 其 provider 配置：新增 `vision` task_type，映射到视觉能力的 chat provider（沿用现有 provider 配置机制）。
  - 修改 `src/fleetent/context_mgr.py`：`estimate_tokens` / 序列化对图片内容块按占位计量，避免把 base64 巨串计入 token 估算。
  - `eval_logger._serialize`：图片块在 trace 中替换为占位（`[图片：{mime}，{大小}]`），避免 trace 写入 base64 巨串。
- **配置**：无新增 Settings 字段（是否多模态由消息内容形态决定，非部署开关）。
- **测试**：新增 `tests/test_multimodal.py`；`tests/test_agent_loop.py` 补充「图片内容块透传 LLM」用例；`tests/test_context_mgr.py` 补充「图片块不撑爆 token 估算」用例。LLM 调用按规范 mock（`patch get_async_client_and_config`）。
- **不影响**：纯文本主循环、终止框架、permission_gate、工具 dispatch、model fallback 的既有行为；不引入新依赖（base64 用标准库）。
