## ADDED Requirements

### Requirement: NormalizedMessage 支持可选文件上传回调

`NormalizedMessage` SHALL 新增 `upload_func: Callable[[list[str]], Awaitable[None]] | None = None` 字段，与现有 `progress_func` 字段对齐。适配器按平台能力决定是否注入；未注入时（`None`）不触发上传。

#### Scenario: upload_func 注入后路由完成时被调用
- **WHEN** `NormalizedMessage.upload_func` 非 None 且本轮有生成图片
- **THEN** `route()` 在 `reply_func` 调用后调用 `upload_func(paths)`，`paths` 为本轮生成图片的本地路径列表

#### Scenario: upload_func 为 None 时安全降级
- **WHEN** `NormalizedMessage.upload_func` 为 None
- **THEN** `route()` 不调用上传，不报错，只发文字响应

### Requirement: normalizer 从本轮工具结果提取生成图片路径

`route()` SHALL 在 `agent_loop.run()` 完成后，仅扫描本轮新增的 tool 消息（`role == "tool"`），从内容中匹配 `"image generated: <path>"` 格式，提取已存在于磁盘的路径列表。路径不存在时跳过。

#### Scenario: 本轮 generate_image 路径被提取
- **WHEN** 本轮 tool 消息含 `"image generated: /path/to/img.png"` 且文件存在
- **THEN** 路径被提取，传给 `upload_func`

#### Scenario: 历史 turn 的旧图片路径不被重复上传
- **WHEN** 历史 turn 中有 `generate_image` 结果，本轮未调用
- **THEN** 这些路径不被提取，不触发上传

#### Scenario: 路径不存在时跳过
- **WHEN** tool 消息含 `"image generated: <path>"` 但文件不存在
- **THEN** 该路径被跳过，不进入 paths 列表

#### Scenario: 非 tool 消息中的路径被忽略
- **WHEN** assistant 或 user 消息中含路径字符串
- **THEN** 不被提取

### Requirement: Slack 适配器上传生成图片到原线程

Slack `_handle()` SHALL 注入 `upload_func`：遍历图片路径列表，调用 `client.files_upload_v2(channel=channel, thread_ts=reply_thread, file=path)` 上传。单个文件上传失败时 MUST 记 warning 并继续上传其余文件，MUST NOT 中断响应。

#### Scenario: 生成图片作为附件发到原线程
- **WHEN** agent 在 Slack DM 或频道调用 `generate_image` 生成图片
- **THEN** 图片作为文件附件发到同一线程，用户直接看到图片

#### Scenario: 单个上传失败优雅降级
- **WHEN** `files_upload_v2` 对某个路径抛异常
- **THEN** 记 warning，跳过该文件，继续处理其余路径，文字响应已正常发出
