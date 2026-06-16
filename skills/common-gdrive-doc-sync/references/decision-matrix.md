# common-gdrive-doc-sync 决策矩阵

## 0. preflight（优先）

在进入上传分支前先做环境判定：
- `google-drive` MCP server 已挂载、工具（`google-drive__*`）可调用
- OAuth 授权有效

若任意失败，直接返回：`DRIVE_MCP_UNAVAILABLE`。

## 1. 可协作编辑（直传）

- `docx`
- `xlsx`
- `pptx`

结果：`status=success`, `mode=direct_upload`, `collaborative_editable=true`

## 2. 可转换后协作（pandoc -> docx）

- `txt`
- `rtf`
- `md`
- `markdown`
- `html`
- `htm`

结果：`status=success`, `mode=converted_upload`, `collaborative_editable=true`

## 3. 可上传但默认不可在线编辑（直传）

- `pdf`
- `odt`
- `ods`
- `odp`

结果：`status=success`, `mode=direct_upload`, `collaborative_editable=false`

## 4. 不可处理（失败）

- 白名单外全部类型（例如：`zip`, `png`, `jpg`, `mp4`）

结果：`status=failed`, `error_code=UNSUPPORTED_FILE_TYPE`

## 5. 错误码矩阵

| 场景 | error_code |
|---|---|
| google-drive MCP server/tool 不可用 | `DRIVE_MCP_UNAVAILABLE` |
| 源文件不存在 | `SOURCE_NOT_FOUND` |
| 源文件不可读 | `SOURCE_NOT_READABLE` |
| 源路径越界 | `SOURCE_OUT_OF_WORKSPACE` |
| 最近产物多文件歧义 | `AMBIGUOUS_ARTIFACT_REFERENCE` |
| 目录参数不合法 | `TARGET_FOLDER_INVALID` |
| 目录链接无法解析 | `TARGET_FOLDER_UNRESOLVABLE` |
| 目录无写权限 | `DRIVE_PERMISSION_DENIED` |
| 文件类型不支持 | `UNSUPPORTED_FILE_TYPE` |
| pandoc 未安装 | `PANDOC_NOT_INSTALLED` |
| 转换命令失败 | `PANDOC_CONVERT_FAILED` |
| 转换输出为空 | `CONVERTED_FILE_EMPTY` |
| Drive 上传失败 | `DRIVE_UPLOAD_FAILED` |
| 上传返回字段异常 | `UPLOAD_RESULT_INVALID` |
| 触发非 MCP 回退分支 | `NON_MCP_FALLBACK_FORBIDDEN` |

## 6. 执行通道约束（V1）

- 仅允许 `google-drive` MCP 工具通道访问 Google Drive。
- 禁止 `rclone`、`gdrive` CLI、手动上传等非 MCP 回退。
