## ADDED Requirements

### Requirement: Telegram 适配器下载非图片文件为文件附件项

Telegram 文件附件下载函数 SHALL 对入站消息中的文档（非图片文件）经 bot API 下载其字节，构造携带原始文件名的文件附件项（`FileAttachment(data, mime, filename)`）加入 `NormalizedMessage.attachments`，镜像 Slack 的非图片文件下载语义。文件大小超过上限（20 MB，与 Slack 一致）时 MUST NOT 下载，SHALL 构造 `data=None` 且 `note` 注明超限的占位项。单个文件下载失败时 handler MUST 记 warning 并构造 `data=None` 且 `note` 注明失败的占位项，MUST NOT 抛异常中断消息处理。图片仍走既有视觉路径（`PHOTO`），MUST NOT 改变。

#### Scenario: 文档被下载为文件附件项

- **WHEN** Telegram 收到一条含文档（非图片文件）的消息
- **THEN** handler 经 bot API 下载其字节，`NormalizedMessage.attachments` 含 `FileAttachment(data=<字节>, mime=<mime>, filename=<原始文件名>)`

#### Scenario: 超过大小上限的文件降级为占位项

- **WHEN** 某个文档的大小超过 20 MB 上限
- **THEN** 该文件不被下载，attachments 含 `data=None` 的占位项，`note` 注明超过大小上限

#### Scenario: 下载失败优雅降级为占位项

- **WHEN** 某个文档下载失败
- **THEN** handler 记 warning，attachments 含 `data=None` 的占位项，`note` 注明接收失败，消息处理不中断

#### Scenario: 图片路径不受影响

- **WHEN** Telegram 收到一条图片消息
- **THEN** 图片仍走既有视觉路径下载，行为不变
