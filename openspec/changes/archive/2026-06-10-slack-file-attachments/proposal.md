## Why

用户在 Slack 上传非图片文件（xlsx / csv / pdf / docx 等）并 @ agent 时，文件被网关**静默丢弃**：`im_gateway/slack.py` 的 `_download_image_attachments` 只下载 `image/*` mime 的文件，其余直接跳过，且 `NormalizedMessage` 没有任何其他字段承载文件信息——agent 视角里这条消息根本没有文件，于是回复「您的消息中似乎没有附带任何表格」（线上 Bug AAA-8053，三条接收路径 assistant 面板 / 频道 @mention / DM 已全部本地复现）。

## What Changes

- Slack 适配器对非图片文件**也下载**（带大小上限），与图片一起进入 `NormalizedMessage.attachments`；文件项携带原始文件名（图片项保持 `(bytes, mime)` 二元组不变）
- normalizer 构建用户消息时，把非图片文件写入该 session 的 **sandbox workspace**（file tools / `run_code` 的唯一可见根），并在消息文本中注入文件引用（原始文件名 + workspace 相对路径），agent 用现有 `read_file` / `run_code` 按需解析
- 非图片文件**不做** vision 式一次性分析（文档不适合一次性摘要，由 agent 按需处理）
- 下载失败 / 超过大小上限时优雅降级：记 warning、注入说明性占位文本，不中断消息处理
- 收窄既有约束：`im-image-attachment` 中「非图片 file MUST 被忽略」改为「非图片 file 交由文件附件通道处理」

## Capabilities

### New Capabilities

- `im-file-attachment`: IM 入站非图片文件的端到端通道——网关下载 → 落入 session workspace → 消息注入文件引用 → agent 经 file tools / sandbox 消费；含大小上限、文件名安全化、失败降级

### Modified Capabilities

- `im-image-attachment`: Slack 适配器 requirement 中「非图片 file MUST 被忽略」收窄为「非图片 file 不进图片通道，交由 im-file-attachment 下载处理」；attachments 契约允许图片二元组之外的文件附件项共存（`_image_attachments` 判据不受影响）

## Impact

- `src/fleetent/im_gateway/slack.py`：`_download_image_attachments` 扩展（或新增伴生函数）下载非图片文件；三条接收路径共用同一函数，一处修复全覆盖
- `src/fleetent/im_gateway/normalizer.py`：`_build_user_content` 新增文件附件分支（写 workspace + 注入引用文本）
- `src/fleetent/integrations/sandbox/manager.py`：复用 `workspace_host_path` 定位 session workspace（只读复用，不改其行为）
- 不改 `runtime/loop.py`、不改 vision / `multimodal-input` 行为（非图片二进制的主循环占位兜底保持原样）
- Telegram 文档附件不在本 change 范围（normalizer 侧通道是平台无关的，Telegram 适配器接入留待后续 change）
- 无 schema / 配置 / 依赖变更
