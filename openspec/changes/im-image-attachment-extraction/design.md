## Context

vision-as-tool(已归档)在 `im_gateway/normalizer.py` 加了含图消息首次自动抽取:`_build_user_content` 调 `_image_attachments(msg.attachments)` 挑出 `(bytes, str-mime 且 image/ 开头)` 项,对每项存盘 + 调一次 `analyze_image`。`NormalizedMessage.attachments: list[Any]`,实际契约是 `list[tuple[bytes, str]]`。

但 `slack.py` / `telegram.py` 的 handler 都硬编码 `attachments=[]`(slack.py:54、telegram.py:59),且 telegram 的 MessageHandler 只注册 `filters.TEXT & ~filters.COMMAND`(photo 消息根本收不到)。所以 IM 端这条 vision 路径无真实数据源。

约束(CLAUDE.md):TDD Hard Gate;禁止 AI 框架;外部 HTTP/SDK 测试全 mock,绝不发真实请求;不吞异常(下载失败 `logger.warning`,不崩 handler);mypy strict;行长 100;只动两个 handler 组装 attachments 这一处,避开张亮 im-gateway connector 工作。

## Goals / Non-Goals

**Goals:**
- Slack/Telegram handler 下载入站图片字节,填入 `NormalizedMessage.attachments`,沿用 normalizer `_image_attachments` 既有判据(`(bytes, image/*-mime)`)。
- 非图片附件忽略;下载失败/无附件 → 空 attachments、不崩(best-effort,记 warning)。
- 纯文本 IM 行为完全不变。

**Non-Goals:**
- 不改 normalizer 抽取逻辑(`_image_attachments` / `_build_user_content` / `_select_route` 复用,不修改)。
- 不碰 connector config/registry/allowlist(张亮 im-gateway-management 域)、session 派生、reply_func、im_user_store。
- 不做附件大小/数量上限、不做缩略图/转码、不做非图片(文档/音视频)附件。

## Decisions

### D1:Slack 用 bot token 鉴权 GET `url_private` 取字节
Slack 消息含文件时 `event["files"]` 是 file 对象列表,每个含 `mimetype` 与 `url_private`。`url_private` 需 `Authorization: Bearer {bot_token}` 才能下载。`handle_message` 里取 `Settings().slack_bot_token`,用 `httpx.AsyncClient` GET 每个 `image/*` file 的 `url_private`,`response.content` 即字节,组装 `(bytes, mimetype)`。
**为何**:`url_private` 是 Slack 官方鉴权下载入口;`httpx` 已是依赖(async 与 bolt AsyncApp 一致)。
**Alternatives**:`files.info` API 二次取——多一次往返且 `url_private` 已在 event 内,被否。

### D2:Telegram 注册加 `filters.PHOTO`,取最大 PhotoSize
当前 handler 只接 `filters.TEXT & ~filters.COMMAND`,photo 消息收不到。改为 `(filters.TEXT | filters.PHOTO) & ~filters.COMMAND`。`handle_message` 里 `update.message.photo` 是 PhotoSize 列表(同一张图多分辨率,末项最大),取最大 → `await context.bot.get_file(file_id)` → `await file.download_as_bytearray()` 取字节 → `attachments=[(bytes(ba), "image/jpeg")]`。telegram photo 统一 jpeg。
**为何**:Telegram photo 无显式 mime,统一 jpeg 与平台行为一致;最大分辨率给 VLM 最多信息。
**Alternatives**:取最小/中间分辨率省带宽——VLM 抽取要清晰度,被否。

### D3:图片消息 text 用 `caption or text or ""`
Telegram 图片消息的文字在 `caption`,不在 `text`。改 text 取值为 `caption or text or ""`,使 normalizer 拿到的 instruction 是用户那句话。纯文本消息无 caption,fallback 到 text,行为不变。
**为何**:vision-as-tool 用 `msg.text` 当 analyze instruction;图片消息文字必须能传进去。

### D4:下载失败优雅降级,attachments 留空,不崩 handler
两个 handler 的下载都 best-effort:逐个附件 try/except,失败 `logger.warning` 记 platform/错误后跳过该附件;无 files/photo → attachments 为 `[]`。任何下载异常都不冒泡到 route。
**为何**:CLAUDE.md「不吞异常→catch 后必须 log」;入站消息处理不能因一张图下载失败而整条丢弃。降级后 normalizer 收到空 attachments,等价纯文本路径。

## Risks / Trade-offs

- [Slack `url_private` 鉴权变化/file 结构差异] → 逐附件 try/except + warning,降级空 attachments,不崩。
- [Telegram 大图下载延迟] → 仅取一张(最大),与本就要处理的首轮合并;失败降级。
- [与张亮 im-gateway-management 同改 slack.py/telegram.py] → 本 change 只动 handler 内 attachments 组装与 telegram filter,不碰 connector 逻辑;merge 时按关注点分块协调(见决策文档跨域节)。
- [非图片附件] → `_image_attachments` 已只挑 `image/*`;handler 侧也只下载 `image/*`,非图直接忽略。

## Open Questions

- 多图消息:Slack 一条消息可含多个 file,本版全部下载组装;Telegram 一条 photo 消息一张,media group 多图为多条 update,本版不特殊处理(每条各自走)。
- 附件大小上限:本版不限,留后续(对称 uploads 生命周期)。
