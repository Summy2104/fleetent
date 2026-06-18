## MODIFIED Requirements

### Requirement: Slack 适配器下载非图片文件为文件附件项

Slack 文件附件下载函数 SHALL 对入站消息 `files` 中每个 mime **不**以 `image/` 开头的 file，用 bot token 鉴权下载其 `url_private` 字节，构造携带原始文件名的文件附件项（`FileAttachment(data, mime, filename)`）加入 `NormalizedMessage.attachments`。文件大小超过上限（20 MB）时 MUST NOT 下载，SHALL 构造 `data=None` 且 `note` 注明超限的占位项。单个文件下载失败时 handler MUST 记 warning 并构造 `data=None` 且 `note` 注明失败的占位项，MUST NOT 抛异常中断消息处理。三条接收路径（assistant 面板 / 频道 @mention / DM）SHALL 共用同一下载函数。

下载所用 HTTP 客户端 SHALL 跟随 HTTP 重定向（`follow_redirects`）。Slack 对部分文件类型（如 PDF 等浏览器内联渲染、可能含活动内容的类型）会把 `url_private`（`files.slack.com`）以 302 跳转到沙箱安全域（`slack-files.com/files-pri-safe/...`，自带签名票鉴权）；该行为由 Slack 服务端按未文档化策略决定、可对任意类型返回，故客户端 SHALL 无条件跟随重定向，MUST NOT 按文件类型特判。跨域重定向时 `Authorization` 头被自动剥除（目标域用签名票鉴权），故跟随重定向不泄露 bot token。

当下载返回的响应 `Content-Type` 为 `text/html`（Slack 在 token scope 不足或文件无权限时返回登录/错误 HTML 页而非文件字节）时，handler MUST NOT 把该 HTML 内容当作文件/图片字节：非图片文件 SHALL 记 warning 并降级为 `data=None` 占位项（`note` 注明接收失败），图片 SHALL 记 warning 并跳过该图片。

#### Scenario: xlsx 文件被下载为文件附件项
- **WHEN** Slack 收到一条含 xlsx file（mime 为 spreadsheet 类型）的消息
- **THEN** handler 用 bot token 下载其 `url_private` 字节，`NormalizedMessage.attachments` 含 `FileAttachment(data=<字节>, mime=<原 mime>, filename=<原始文件名>)`

#### Scenario: 超过大小上限的文件降级为占位项
- **WHEN** 某个非图片 file 的 size 超过 20 MB 上限
- **THEN** 该文件不被下载，attachments 含 `data=None` 的占位项，`note` 注明超过大小上限

#### Scenario: 下载失败优雅降级为占位项
- **WHEN** 某个非图片 file 的 `url_private` 下载失败
- **THEN** handler 记 warning，attachments 含 `data=None` 的占位项，`note` 注明接收失败，消息处理不中断

#### Scenario: 三条接收路径行为一致
- **WHEN** 同一含 xlsx 的消息分别经 assistant 面板、频道 @mention、DM 路径进入
- **THEN** 三条路径产出的文件附件项一致（共用同一下载函数）

#### Scenario: 302 跳转到沙箱安全域的文件被成功下载
- **WHEN** 某个非图片 file（如 PDF）的 `url_private` 返回 302 跳到 `slack-files.com/files-pri-safe/...`
- **THEN** 下载客户端跟随该重定向并取得真实文件字节，attachments 含 `data=<字节>` 的文件附件项（不再降级为失败占位）

#### Scenario: 返回 HTML 时降级而非当作文件字节
- **WHEN** 某个非图片 file 的下载响应 `Content-Type` 为 `text/html`（token scope / 权限问题导致的登录或错误页）
- **THEN** handler 记 warning，attachments 含 `data=None` 占位项（`note` 注明接收失败），HTML 内容 MUST NOT 作为文件字节进入 attachments

#### Scenario: 图片返回 HTML 时被跳过
- **WHEN** 某个图片 file 的下载响应 `Content-Type` 为 `text/html`
- **THEN** handler 记 warning 并跳过该图片，HTML 内容 MUST NOT 作为图片字节进入 attachments
