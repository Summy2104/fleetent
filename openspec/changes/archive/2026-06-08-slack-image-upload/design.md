## Context

`NormalizedMessage.reply_func` 签名为 `(text: str) -> None`，只能发送文字。`generate_image` 工具将图片写盘后返回 `"image generated: <path>"`，agent loop 将此路径传给 LLM 生成文字描述，最终只有文字经 `reply_func` 发出，图片文件从未送达用户。

现有 `NormalizedMessage` 已有 `progress_func: ... | None` 的可选回调模式，适合扩展。

## Goals / Non-Goals

**Goals:**
- Slack 用户收到 `generate_image` 结果时能直接看到图片附件
- 其他适配器（Telegram 等）不受影响（`upload_func` 默认 None）
- 单个文件上传失败不中断整体响应

**Non-Goals:**
- 修改 `reply_func` 签名（破坏现有适配器）
- 支持 Telegram 图片上传（独立 change）
- 上传非 `generate_image` 产生的文件

## Decisions

### D1：`upload_func` 作为 NormalizedMessage 的可选回调

对齐 `progress_func` 模式：`upload_func: Callable[[list[str]], Awaitable[None]] | None = None`。  
适配器按需注入，normalizer 在 loop 结束后调用——解耦适配器能力与路由逻辑。

### D2：提取逻辑基于本轮新增的 history 消息

`agent_loop.run()` 前记 `history_len = len(history)`，之后只扫 `history[history_len:]`，避免误触历史 turn 中的旧图片路径。

### D3：正则匹配 `generate_image` 工具结果格式

`builtin_tools.generate_image` 返回 `f"image generated: {ref}"`，格式稳定。用 `re.search(r"image generated: (.+)", content)` 提取路径，再用 `Path(p).is_file()` 过滤不存在的路径（失败时跳过，不报错）。

### D4：Slack 使用 `files_upload_v2`

`slack_sdk` 已内置 `AsyncWebClient.files_upload_v2()`，无需新依赖。上传到原线程（`thread_ts=reply_thread`）。

## Risks / Trade-offs

- **[Risk] `files_upload_v2` API 兼容性** → 对 slack_sdk 版本有要求（≥3.19）；若失败 log warning 降级为只发文字，不影响核心功能
- **[Risk] 路径格式变化** → 若 `generate_image` 返回格式修改，正则失效。正则只用于 tool 消息，影响面局限
