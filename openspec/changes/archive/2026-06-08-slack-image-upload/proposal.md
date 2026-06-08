## Why

`generate_image` 工具生成图片后仅返回本地文件路径，Slack adapter 的 `reply_func` 只能发送文字，图片文件从未上传到 Slack，用户在频道中看不到生成的图片——只有文字描述。

## What Changes

- **新增** `NormalizedMessage.upload_func` 可选回调字段，对齐现有 `progress_func` 模式，供适配器注入平台原生文件上传能力
- **新增** `normalizer._extract_generated_image_paths()`：扫描本轮新增的 tool 结果，正则匹配 `generate_image` 返回的 `"image generated: <path>"` 格式，提取已存在的本地文件路径
- **修改** `normalizer.route()`：在 `agent_loop.run()` 完成后，提取本轮生成的图片路径，若 `upload_func` 非 None 则调用
- **修改** `slack.py` `_handle()`：实现 `upload_func`，调用 `client.files_upload_v2()` 将图片作为附件发到原线程，单个失败 log warning 不中断

## Capabilities

### New Capabilities

- `im-generated-image-upload`: IM 网关在 agent loop 完成后，识别本轮生成的图片并通过平台原生 API 上传，使用户能在 IM 中直接看到生成的图片

### Modified Capabilities

- `im-image-attachment`: 现有 spec 覆盖入站图片（下载 → attachments）；本次在同一 IM 图片附件域新增出站方向（生成 → 上传）

## Impact

- `src/fleetent/im_gateway/normalizer.py`：新增字段和辅助函数，修改 `route()` 尾部逻辑
- `src/fleetent/im_gateway/slack.py`：新增 `upload_func` 实现，传入 `NormalizedMessage`
- `tests/unit/`：新增测试（路径提取、route 调用 upload_func、upload_func=None 时安全降级）
- 无新外部依赖（`files_upload_v2` 已在 slack-sdk 中）
- Telegram 等其他适配器不受影响（`upload_func` 默认 None）
