## Why

`slack-image-upload` 修复（PR #194）让 `generate_image` 生成的图片能自动上传到 Slack，但同一机制不覆盖 `write_file` 工具——用户请求 bot 生成文件后，Slack 只收到文字描述，文件存在本地磁盘但从未送达用户。

## What Changes

- **修改** `normalizer._extract_generated_image_paths()`：新增第二个匹配模式，同时匹配 `write_file` 工具输出格式 `"written N bytes to <path>"`（原有 `"image generated: <path>"` 不变）
- **新增** `_FILE_WRITTEN_RE` 正则常量

## Capabilities

### New Capabilities

（无新能力——扩展已有能力的覆盖范围）

### Modified Capabilities

- `im-generated-image-upload`: 当前只覆盖 `generate_image` 工具；扩展为同时覆盖 `write_file` 工具，使所有 agent 生成/写入的本地文件都能上传到 Slack

## Impact

- `src/fleetent/im_gateway/normalizer.py`：扩展 `_extract_generated_image_paths()` 和新增正则常量
- `tests/unit/test_slack_image_upload.py`：新增两个测试用例
- `slack.py`、`NormalizedMessage`、`upload_func` 逻辑无需修改
