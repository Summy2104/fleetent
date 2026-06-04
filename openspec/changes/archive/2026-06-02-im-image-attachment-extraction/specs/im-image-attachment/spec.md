## ADDED Requirements

### Requirement: Slack 适配器下载入站图片填入 attachments

Slack `handle_message` SHALL 读取入站消息的 `files` 字段,对每个 `mimetype` 以 `image/` 开头的 file,用 bot token 鉴权下载其 `url_private` 字节,并将 `(bytes, mimetype)` 加入 `NormalizedMessage.attachments`。非图片 file MUST 被忽略。消息无 file 时 attachments MUST 为空列表。下载某个图片失败时 handler MUST 记 warning 并跳过该图片,MUST NOT 抛异常中断消息处理。

#### Scenario: 含图片消息下载并填入 attachments
- **WHEN** Slack 收到一条含 `image/*` file 的消息
- **THEN** handler 用 bot token 鉴权下载其 `url_private` 字节,`NormalizedMessage.attachments` 含对应的 `(bytes, mimetype)` 项

#### Scenario: 非图片 file 被忽略
- **WHEN** Slack 消息的 file 是非 `image/` 类型(如 PDF)
- **THEN** 该 file 不被下载、不进入 attachments

#### Scenario: 无 file 消息 attachments 为空
- **WHEN** Slack 收到一条不含 file 的纯文本消息
- **THEN** `NormalizedMessage.attachments` 为空列表,行为与改动前一致

#### Scenario: 下载失败优雅降级
- **WHEN** 某个图片 file 的 `url_private` 下载失败
- **THEN** handler 记 warning、跳过该图片,不抛异常中断消息处理

### Requirement: Telegram 适配器接收 photo 消息并下载图片填入 attachments

Telegram 的消息 handler 注册 SHALL 同时接收 photo 消息(在文本 filter 基础上加 `filters.PHOTO`)。处理 photo 消息时,handler SHALL 取 `update.message.photo` 中分辨率最大的一张,经 `context.bot.get_file` 下载其字节,将 `(bytes, "image/jpeg")` 加入 `NormalizedMessage.attachments`,并以 `caption or text or ""` 作为消息文本。纯文本消息行为 MUST 不变。下载失败时 handler MUST 记 warning 并降级为空 attachments,MUST NOT 抛异常中断消息处理。

#### Scenario: photo 消息下载并填入 attachments
- **WHEN** Telegram 收到一条含 photo 的消息
- **THEN** handler 取最大分辨率 PhotoSize,经 `get_file` 下载字节,`NormalizedMessage.attachments` 含 `(bytes, "image/jpeg")`

#### Scenario: 图片消息文字取自 caption
- **WHEN** Telegram photo 消息带 caption
- **THEN** `NormalizedMessage.text` 为该 caption(图片消息文字在 caption 而非 text)

#### Scenario: 纯文本消息行为不变
- **WHEN** Telegram 收到一条纯文本消息
- **THEN** `NormalizedMessage.attachments` 为空列表,`text` 取自消息 text,行为与改动前一致

#### Scenario: 下载失败优雅降级
- **WHEN** photo 下载(`get_file` 或字节下载)失败
- **THEN** handler 记 warning、降级为空 attachments,不抛异常中断消息处理

### Requirement: attachments 契约与 vision 抽取判据一致

适配器组装的 `NormalizedMessage.attachments` 项 MUST 为 `(bytes, str)` 二元组,其中第二元为以 `image/` 开头的 MIME 字符串,使其满足 normalizer `_image_attachments` 既有判据并触发 vision-as-tool 的含图自动抽取。本 change MUST NOT 修改 normalizer 的抽取逻辑。

#### Scenario: 组装项被 normalizer 识别为图片
- **WHEN** 适配器将一张下载的图片以 `(bytes, "image/png")` 形式放入 attachments
- **THEN** normalizer 的 `_image_attachments` 将其识别为图片项,交由 vision-as-tool 自动抽取
