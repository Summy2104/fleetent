# 路径说明（fleetent）

## 结论：无需路径转换

fleetent 下 agent 工具与 MCP 工具共享同一套 workspace 相对路径，**不存在** OpenClaw 那种
「容器内 `/workspace` ↔ 宿主机路径」的转换问题：

- `read_file` / `write_file` / `edit_file`、`pandoc`（经 `bash_exec`）：用 workspace 相对路径
- `google-drive` MCP 工具的 `localPath`：同样用 workspace 相对路径（或 `/exchange/...` 路径）
- `send_file`：用 workspace 相对路径（或 `/exchange/...` 路径）

因此本 skill 全程只用 workspace 相对路径，不做任何路径拼接或转换。

## 路径使用规则

| 工具 | 需要路径类型 | 示例 |
|------|------------|------|
| `read_file`/`write_file`/`edit_file` | workspace 相对 | `media/inbound/report.docx` |
| `pandoc`（via `bash_exec`） | workspace 相对 | `notes.md` → `outbound/gdrive-sync/notes.docx` |
| `google-drive__uploadFile` | workspace 相对 | `outbound/gdrive-sync/notes.docx` |
| `send_file` | workspace 相对 / `/exchange` | `outbound/gdrive-sync/notes.docx` |

## 完整示例

### 示例 1：上传 workspace 内文件

```
google-drive__uploadFile(
  localPath="media/inbound/report.docx",
  parentFolderId="1ABC123xyz"
)
```

### 示例 2：转换并上传 Markdown

```
# 步骤 1：转换（输出到 workspace 相对目录）
bash_exec: mkdir -p outbound/gdrive-sync && pandoc "notes.md" -o "outbound/gdrive-sync/notes.docx"

# 步骤 2：上传
google-drive__uploadFile(localPath="outbound/gdrive-sync/notes.docx", parentFolderId="1ABC123xyz")
```

## 最佳实践

1. **统一用 workspace 相对路径**：不要用 `/tmp` 等沙盒外绝对路径
2. **转换文件输出到 `outbound/`**：推荐 `outbound/gdrive-sync/` 便于管理
3. **上传前确认文件存在**：可用 `read_file` 或 `bash_exec: ls` 验证
