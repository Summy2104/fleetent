# im-file-attachment Specification

## Purpose
入站非图片文件（xlsx / csv / pdf / docx 等）从 IM 平台到 agent 的端到端通道：网关用 bot token 下载文件字节 → 写入该 session 的 sandbox workspace → 在用户消息中注入 workspace 相对路径引用 → agent 经 `read_file` / `run_code` 按需读取。含大小上限、文件名安全化与失败降级，确保文件不再被静默丢弃，且与图片通道、主循环二进制隔离。

## Requirements

### Requirement: Slack 适配器下载非图片文件为文件附件项

Slack 文件附件下载函数 SHALL 对入站消息 `files` 中每个 mime **不**以 `image/` 开头的 file，用 bot token 鉴权下载其 `url_private` 字节，构造携带原始文件名的文件附件项（`FileAttachment(data, mime, filename)`）加入 `NormalizedMessage.attachments`。文件大小超过上限（20 MB）时 MUST NOT 下载，SHALL 构造 `data=None` 且 `note` 注明超限的占位项。单个文件下载失败时 handler MUST 记 warning 并构造 `data=None` 且 `note` 注明失败的占位项，MUST NOT 抛异常中断消息处理。三条接收路径（assistant 面板 / 频道 @mention / DM）SHALL 共用同一下载函数。

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

### Requirement: 文件附件写入 session sandbox workspace

normalizer 构建用户消息内容时，SHALL 将每个 `data` 非空的文件附件项写入该 session 的 sandbox workspace 的 `uploads/` 子目录（经 sandbox manager 的 `workspace_host_path(scope, session_id, agent_name)` 定位 host 目录），使 `read_file` / `run_code` 在容器与 host-degrade 两种模式下均可按 workspace 相对路径访问。写盘前 SHALL 对原始文件名做安全化：basename 化、剥离路径分隔符与控制字符、保留扩展名，空名回退 `file`；与已有文件同名时 SHALL 加唯一前缀避免覆盖。写盘 MUST NOT 触发 docker 连接（host 无 docker 时同样可用）。

#### Scenario: 文件落入 workspace 并可按相对路径访问
- **WHEN** 一个 xlsx 文件附件项进入 normalizer
- **THEN** 字节被写入该 session workspace 的 `uploads/` 子目录，注入消息的相对路径在该 workspace 围栏内可解析

#### Scenario: 恶意文件名被安全化
- **WHEN** 文件附件项的 filename 含路径分隔符或 `..`（如 `../../etc/passwd`）
- **THEN** 写盘文件名被 basename 化且剥离危险字符，文件仍只落在 workspace 的 `uploads/` 子目录内

#### Scenario: 同名文件不被覆盖
- **WHEN** 两条消息先后携带同名文件
- **THEN** 第二个文件以唯一前缀写盘，第一个文件内容不被覆盖

### Requirement: 用户消息注入文件引用文本

normalizer 构建用户消息内容时，对每个文件附件项 SHALL 在用户文本后追加一段文件引用：`data` 非空时为「文件 {原始文件名} 已保存到 {workspace 相对路径}，可用 read_file 或 run_code 读取」语义的文本；`data=None` 时为「文件 {原始文件名} 未能接收：{note}」语义的占位说明。无文件附件项的消息 MUST 保持现状（纯文本或仅图片流程），行为与改动前一致。文件 MUST NOT 做 vision 式一次性自动分析。

#### Scenario: 成功接收的文件注入路径引用
- **WHEN** 用户在 Slack 发「总结表格内容」并附 xlsx 文件
- **THEN** agent 收到的用户消息含原文本与文件引用（原始文件名 + workspace 相对路径 + 工具提示），agent 可据此用 run_code 解析文件

#### Scenario: 未能接收的文件注入占位说明
- **WHEN** 附件超限或下载失败（`data=None` 占位项）
- **THEN** 用户消息含「未能接收」及原因的占位文本，agent 不会声称没有收到文件

#### Scenario: 无文件消息行为不变
- **WHEN** 消息不含任何文件附件项
- **THEN** 用户消息构建行为与改动前完全一致

### Requirement: 文件附件不进入图片通道与主循环二进制

文件附件项 MUST NOT 满足 normalizer `_image_attachments` 的图片判据，MUST NOT 触发 vision 路由或 vision 一次性分析；文件字节 MUST NOT 以二进制或 base64 形式进入主循环上下文——主循环只见文本引用。

#### Scenario: 文件不触发 vision
- **WHEN** 消息只含 xlsx 文件附件项、无图片
- **THEN** 不发生 vision 调用，主循环按纯文本路由

#### Scenario: 图片与文件混合各走各通道
- **WHEN** 消息同时含一张 png（二元组）与一个 xlsx（文件附件项）
- **THEN** png 走既有 vision 抽取注入，xlsx 走文件落盘 + 路径引用注入，互不干扰
