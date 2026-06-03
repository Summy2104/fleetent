## Context

`agent_loop.run()` 接收 `messages: list[dict[str, Any]]`，`run_stream()` 接收 `user_input: str` 并自行组装 `{"role": "user", "content": user_input}`。整条链路把 `content` 当字符串：`maybe_compress`（context_mgr）按 `len(str(m))` 估 token，`log_run` 直接序列化 messages，`user_input` 提取（行 258-261）取第一条 user 消息的 `content`。

OpenAI 兼容 chat API 的 `content` 既可为 `str`，也可为内容块数组 `[{"type": "text", "text": ...}, {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}]`。本 change（AR21）让平台接受图片内容块并透传支持视觉的 LLM，base64 内联保证数据不出内网。范围限定输入侧透传 + 与既有模块（压缩、trace、消息卫生）的协调，不触碰工具层与输出。

约束（CLAUDE.md）：禁止 AI 框架；禁止云托管专有服务（图片走 base64 内联，不用外部图床/对象存储，符合数据主权）；禁止全局可变状态；新模块结构为 import → 常量 → 数据类 → 函数；mypy strict；TDD Hard Gate；base64 用标准库不引新依赖。

## Goals / Non-Goals

**Goals:**
- 主循环接受 `content` 为文本+图片内容块数组并原样透传 LLM。
- 图片以 base64 data URL 内联承载（`image_url` 块），数据不出内网。
- 检测图片块并路由到 `vision` task_type（视觉模型）；未配置 vision 路由时明确报错。
- 提供构造辅助把（文本 + 图片）组装为合法内容块消息，供入口复用。
- 纯文本路径完全向后兼容。
- 压缩 / trace / 消息卫生对含图片块的消息不崩溃（按占位计量与序列化）。

**Non-Goals:**
- 不支持音频 / 视频输入（明确边界）。
- 不实现 IM 平台（Slack/Telegram）的附件下载与解码（属各 adapter 范围；本次提供构造辅助供其调用）。
- 不实现图片缩放 / 压缩 / OCR 等预处理。
- 不改动工具层、输出、终止框架、fallback 的既有行为；不新增 Settings 字段。

## Decisions

### D1：content 放宽为「str | 内容块数组」，透传不解释
`run()` 的 `messages` 元素 `content` 类型放宽为 `str | list[dict]`；主循环不解释内容块语义，原样传给 `_call_with_fallback` / `_stream_with_fallback`（SDK 已支持数组形态）。新增 `is_multimodal_content(content) -> bool` 判定（content 为 list 即多模态）。
**为何**：透传是最小且最稳的接入方式——SDK 与后端已原生支持内容块数组，平台无需理解图片语义；纯文本仍走 str 快路径，零行为变更。
**Alternatives**：①自定义中间表示再转换——被否，多一层无收益的抽象；②把图片转存外部图床传 URL——被否，违反数据主权（云托管/外部存储），base64 内联才符合「数据不出内网」。

### D2：base64 data URL 内联承载图片
`multimodal.py` 提供 `build_image_block(data: bytes, mime: str) -> dict`：用标准库 `base64.b64encode` 生成 `{"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}}`；`build_message_with_images(text, images) -> dict` 组装含文本块 + 多个图片块的 user 消息。
**为何**：base64 内联使图片数据随消息体走，全程留在内网，不依赖任何外部存储服务；标准库实现，无新依赖。
**Alternatives**：远程 URL 形式的 image_url——被否，需图片可被 LLM 后端访问，破坏内网边界。

### D3：压缩 / trace / 卫生对图片块按占位处理
- `context_mgr.estimate_tokens`：图片内容块不按 `len(str(...))` 计（base64 巨串会把估算撑爆导致误压缩），改为图片块计固定占位 token（如每图固定常量），文本块按字符估。
- `eval_logger._serialize`：图片块在 trace 中替换为 `[图片：{mime}，{字节数}]` 占位，避免 base64 巨串写入 JSONL。
- 消息卫生（若 message-hygiene 已合入）：图片内容块视为合法 user content，不触发同角色/孤立修复误判；本 change 仅确保不崩溃，卫生规则细节归 AR6。
**为何**：base64 字符串极长，若不占位会污染 token 估算（误触发压缩）与 trace 可读性/体积。占位计量与序列化是局部、可单测的协调改动。
**Open**：每图占位 token 常量取值需结合后端对图片的实际计费/计量经验设定（见 Open Questions）。

### D4：非图片二进制归一化为文本占位
输入若含非图片、非文本的二进制内容（如 PDF/音视频字节），不透传，归一化为文本占位提示（如 `[不支持的附件类型：{mime}]`）。`build_message_with_images` 仅接受图片 mime，其它类型由调用方或辅助函数转占位。
**为何**：明确边界（音视频不支持），且避免把无法被视觉模型理解的二进制塞进 image_url 造成后端报错。
**Alternatives**：直接拒绝含非图片附件的请求——被否，损失用户已发的文本部分；占位降级更友好。

### D5：user_input 提取兼容内容块数组
`run()` 中 `user_input` 提取（行 258-261，供 trace 与 `extract_and_save`）当 content 为数组时，取其中文本块拼接；无文本块则空串。
**为何**：trace 与记忆提取依赖文本 user_input；数组 content 下需降级取文本，不能 `str(content)` 写入 base64 巨串。

### D6：检测图片块 → 路由到 vision task_type（无则报错，方案 A）
- 新增 `has_image_block(messages) -> bool`：具体识别消息中的 `image_url` 内容块（区别于仅判断 content 是否为数组的 `is_multimodal_content`——数组也可能只有文本块）。
- 主循环（`run()` / `run_stream()`）在取 client 前判断：`has_image_block` 为真 → `get_async_client_and_config("vision")`，否则 `"default"`，行为与现状一致。
- model_router 配置新增 `vision` task_type，映射到视觉能力的 chat provider（沿用其现有 provider 配置机制；vision 仍是 chat completion，故归 model_router 而非工具）。
- **无视觉路由兜底（方案 A）**：含图片但 `vision` task_type 未配置 → 抛明确错误（如「未配置视觉模型，无法处理图片输入」），不静默发给非视觉模型撞远端 400。

**为何**：透传图片若不路由到视觉模型会被后端拒，AR21 单独落地将是半成品；以 `task_type="vision"` 而非 MR1 的 `force_model` 承载，因为「有图→视觉模型」是**长期路由规则**而非一次性覆盖，且不依赖 MR1（解耦）。报错而非静默降级，符合 CLAUDE.md「异常不吞」。
**Alternatives**：①保持纯透传不路由——被否，半成品，图片实际用不了；②用 MR1 `force_model` 覆盖——被否，应是 task_type 级长期规则，不应每次调用方手动指定；③无 vision 路由时降级丢图发文本——被否（用户选方案 A），静默降级掩盖配置缺失。
**注**：文生图（text-to-image）是**另一回事**——它是「文本→图」的输出型操作，走独立的 `generate_image` 工具（见 change `image-generation-tool`），不在本 change 的 vision 输入路由范围内。

## Risks / Trade-offs

- [base64 图片污染 token 估算导致误压缩] → `estimate_tokens` 对图片块改占位计量，单测「含大图消息的估算不爆」。
- [base64 巨串写入 trace 撑爆 JSONL] → `_serialize` 图片块转占位，单测断言 trace 不含 base64。
- [所选模型不支持视觉时透传图片块会被后端拒] → 本 change 检测图片块并路由到 `vision` task_type（D6）；未配置 vision 路由时明确报错（方案 A），不静默撞 400。
- [纯文本路径意外受影响] → content 为 str 时全程走原路径，`is_multimodal_content` 仅在 list 时为真；保留并扩展现有纯文本用例确保零回归。
- [与消息卫生/压缩的协调遗漏边界] → 本次仅保证「不崩溃 + 占位计量/序列化」，深层卫生规则归 AR6；用例覆盖含图片块的压缩与 trace。

## Open Questions

- 每张图片在 `estimate_tokens` 中占位 token 的取值——实现首步结合后端图片计量经验定一个保守常量，后续可随实际用量校准。
- IM adapter（Slack/Telegram）如何获取图片字节并调用构造辅助——本 change 只提供辅助函数，adapter 接入是各自后续工作；确认辅助函数签名满足其需要。
