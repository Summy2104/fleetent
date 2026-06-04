## Why

vision-as-tool(已归档)让 `im_gateway/normalizer.py` 在消息含图时自动抽取:对每个 `(bytes, mime)` 图片附件存盘并调一次 `analyze_image`,挑选判据是 `_image_attachments(msg.attachments)`(`(bytes, str-mime 且 image/ 开头)`)。但 `slack.py` / `telegram.py` 两个 handler 都硬编码 `attachments=[]`,IM 端这条路径**没有真实数据源**——用户在 Slack/Telegram 发的图永远到不了 vision 抽取。本 change 补上适配器的入站图片下载。

## What Changes

- **Slack handler**:`handle_message` 读 `event.get("files")`,对 `mimetype` 以 `image/` 开头的 file 用 bot token 鉴权下载其 `url_private` 字节,组装 `attachments=[(bytes, mimetype), ...]` 传入 `NormalizedMessage`(替换硬编码 `[]`)。非图片 file 忽略;下载失败/无 files → 空 attachments、不崩(best-effort,记 warning)。
- **Telegram handler**:注册 filter 扩展为也接收 photo 消息;`handle_message` 取 `update.message.photo` 最大一张,经 `context.bot.get_file` 下载字节,组装 `attachments=[(bytes, "image/jpeg")]`;`text` 改用 `caption or text or ""`(图片消息文字在 caption)。纯文本消息行为不变;下载失败 → 空 attachments、不崩。
- **不改** normalizer 抽取逻辑、connector config/registry、session 派生、reply_func、im_user_store——只动两个 handler 组装 attachments 这一处(最小改动,避开 im-gateway connector 工作)。

## Capabilities

### New Capabilities
- `im-image-attachment`: IM 适配器(Slack/Telegram)下载入站图片字节并填入 `NormalizedMessage.attachments`(`list[tuple[bytes, str]]`,mime 以 `image/` 开头),接通 vision-as-tool 既有的 IM 含图自动抽取;非图片附件忽略,下载失败或无附件优雅降级为空 attachments、不中断 handler。

### Modified Capabilities
<!-- vision-as-tool(已归档)的 normalizer 抽取契约不改;本 change 只为其补上 IM 端数据源,不修改既有需求。 -->

## Impact

- **代码**:
  - `src/fleetent/im_gateway/slack.py`:`handle_message` 读 `event["files"]`、过滤 `image/*`、httpx async GET `url_private`(`Authorization: Bearer {bot_token}`)取字节,组装 attachments。
  - `src/fleetent/im_gateway/telegram.py`:注册 filter 加 `filters.PHOTO`,`handle_message` 取最大 PhotoSize → `get_file` → `download_as_bytearray` 取字节,组装 attachments;text 用 caption fallback。
- **依赖**:`httpx` 已在依赖中(Slack 下载用),`python-telegram-bot` / `slack-bolt` 既有;无新依赖。
- **测试**:slack 下载用 httpx mock(unittest.mock)、telegram `get_file` / download 用 unittest.mock;含图→attachments 含 `(bytes, image/*)`;非图忽略;下载失败→空 attachments 不崩;纯文本行为不变。
- **不影响**:normalizer `_image_attachments` / `_build_user_content` 抽取逻辑、`_select_route`、connector registry/allowlist/config、session 派生、im_user_store。

## Dependencies

- 复用 vision-as-tool(已归档)的 `NormalizedMessage.attachments` 契约与 `_image_attachments` 判据(`(bytes, str-mime 且 image/ 开头)`)。
- 复用 slack-telegram-mvp(已归档)的两个 handler 骨架与 `create_app` 结构。
