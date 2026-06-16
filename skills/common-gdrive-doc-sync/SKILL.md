---
name: common-gdrive-doc-sync
description: 将文档同步到 Google Drive 可选目录（支持 folderId/目录链接）。策略为可协作编辑优先；不可协作但可转换时使用 pandoc 转 docx 后上传。触发词：gdrive同步、同步到 gdrive、Google Drive同步、上传到GoogleDrive、同步到Google Drive共享目录、同步到共享目录、folderId 上传。
status: active
metadata:
  author: RD Team
  version: 1.0.0
complexity: L3
---

# Google Drive 文档同步

将本地文件或会话中最近生成的文件同步到 Google Drive 指定目录。

## 前置条件

通过 `google-drive` MCP 工具访问 Google Drive 数据（工具名格式 `google-drive__<tool>`，双下划线，参数照传）。需确保：
- `google-drive` MCP server 已挂载并完成 OAuth 授权
- 用户对目标目录有写入权限
- 已安装 pandoc（用于文件格式转换）

> 执行策略为 `MCP-only`：禁止 `rclone`、`gdrive` CLI、手动上传等非 MCP 回退路径。

### 路径说明（fleetent）

文件用 workspace 相对路径引用（如 `media/inbound/report.docx`、`outbound/gdrive-sync/notes.docx`）。`pandoc` 经 `bash_exec` 在沙箱内运行，输入输出都用 workspace 相对路径；`google-drive` MCP 工具的 `localPath` 同样用 workspace 相对路径（或 `/exchange/...` 路径），无需任何宿主机路径拼接或 agent_id 转换。

## Google Drive MCP 工具说明

工具名格式 `google-drive__<tool>`：

| 工具 | 用途 | 示例 |
|------|------|------|
| `google-drive__uploadFile` | 上传文件到指定目录 | 上传文档、图片 |
| `google-drive__createFolder` | 创建文件夹 | 组织文件结构 |
| `google-drive__listFolder` | 列出目录内文件 | 查看目录内容 |
| `google-drive__deleteItem` | 删除文件 | 清理旧文件 |

#### 常用参数

| 参数 | 用途 | 示例 |
|------|------|------|
| `localPath` | 本地文件路径（workspace 相对） | `media/inbound/document.docx` |
| `parentFolderId` | 目标文件夹 ID | `1ABC123xyz` |
| `name` | 上传后的文件名 | `report.docx`（可选） |
| `mimeType` | MIME 类型 | `application/pdf`（可选） |

## 输入契约

- `source_path`：本地文件绝对路径（优先）
- `target_folder`：Google Drive 目录（`folderId` 或目录链接）
- `filename_override`：可选，上传文件名覆盖
- `mime_hint`：可选，辅助识别

## 会话文件识别

当用户未提供 `source_path` 时：
1. 仅允许自动识别“最近一次会话产出的单个文件”
2. 最近一次为多个文件时返回 `AMBIGUOUS_ARTIFACT_REFERENCE`
3. 无可识别产物时返回 `SOURCE_NOT_FOUND`

## 目录参数处理

1. `target_folder` 为 `folderId`：直接使用
2. 为目录链接：解析出 `folderId`
3. 无法解析：返回 `TARGET_FOLDER_UNRESOLVABLE`

## 工作流程

### Step 1: 参数确认与 preflight

从用户输入中识别或询问：

| 参数 | 必填 | 说明 | 示例 |
|------|------|------|------|
| source_path | 是 | 本地文件路径（workspace 相对） | `report.md` |
| target_folder | 是 | 目标目录 | folderId 或目录链接 |
| filename_override | 否 | 自定义文件名 | `final_report.docx` |

**目录参数处理**：
1. `target_folder` 为 `folderId`：直接使用
2. 为目录链接：解析出 `folderId`（从 URL 提取）
3. 无法解析：返回 `TARGET_FOLDER_UNRESOLVABLE`

**Preflight 检查**（可选，用于提前发现问题）：调用一次轻量的 `google-drive__listFolder`（或任意只读工具）确认 server 可达。

说明：若 `google-drive` MCP server 不可用，返回 `DRIVE_MCP_UNAVAILABLE`。

### Step 2: 四分类决策（严格在线编辑语义）

- **A 直传且可在线编辑**：`docx`/`xlsx`/`pptx` -> `direct_upload`，`collaborative_editable=true`
- **B 转换后可在线编辑**：`txt`/`rtf`/`md`/`markdown`/`html`/`htm` -> `pandoc -> .docx` -> `converted_upload`，`collaborative_editable=true`
- **C 可上传但默认不可在线编辑**：`pdf`/`odt`/`ods`/`odp` -> `direct_upload`，`collaborative_editable=false`
- **D 不可处理**：白名单外类型 -> 失败（`UNSUPPORTED_FILE_TYPE`）

### Step 3: 执行上传

文件路径全程使用 workspace 相对路径，`google-drive__uploadFile` 的 `localPath` 直接传该相对路径，无需任何路径转换。

#### A. 直传（docx/xlsx/pptx/pdf）

```
google-drive__uploadFile(localPath="{source_path}", parentFolderId="{folderId}")
```

返回示例：
```json
{
  "id": "1XYZ789abc",
  "name": "document.docx",
  "mimeType": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
}
```

#### B. 转换后上传（md/txt/html）

**步骤 1**：转换为 docx（输出到 workspace 相对目录）
```
bash_exec: mkdir -p outbound/gdrive-sync && pandoc "{source_path}" -o "outbound/gdrive-sync/{filename}.docx"
```

**步骤 2**：上传转换后的文件
```
google-drive__uploadFile(localPath="outbound/gdrive-sync/{filename}.docx", parentFolderId="{folderId}")
```

### Step 4: 结构化回执

成功输出：
```json
{
  "status": "success",
  "mode": "direct_upload|converted_upload",
  "drive_file_id": "<fileId>",
  "drive_folder_id": "<folderId>",
  "uploaded_name": "<name>",
  "collaborative_editable": true
}
```

说明：`collaborative_editable` 必须按分类返回，A/B 为 `true`，C 为 `false`，不得固定值。

失败输出：
```json
{
  "status": "failed",
  "error_code": "<ERROR_CODE>",
  "message": "<error_message>",
  "details": {}
}
```

## 错误码

- `SOURCE_NOT_FOUND`
- `SOURCE_NOT_READABLE`
- `SOURCE_OUT_OF_WORKSPACE`
- `AMBIGUOUS_ARTIFACT_REFERENCE`
- `TARGET_FOLDER_INVALID`
- `TARGET_FOLDER_UNRESOLVABLE`
- `DRIVE_PERMISSION_DENIED`
- `UNSUPPORTED_FILE_TYPE`
- `PANDOC_NOT_INSTALLED`
- `PANDOC_CONVERT_FAILED`
- `CONVERTED_FILE_EMPTY`
- `DRIVE_UPLOAD_FAILED`
- `UPLOAD_RESULT_INVALID`
- `DRIVE_MCP_UNAVAILABLE`
- `NON_MCP_FALLBACK_FORBIDDEN`

## 首轮契约（用于测试与实现对齐）

1. direct（信息充分）
- 首轮直接返回结构化结果（成功或失败）
- 成功必须包含：`status`、`mode`、`drive_file_id`、`collaborative_editable`

2. clarify（信息不足）
- 首轮先说明缺口并请求最小补充项
- 此场景不得宣称“已完成上传”

3. 禁止审批型回复
- 不得输出“请批准命令后继续”“需要授权执行命令”等审批型文案
- 在测试语境（包含“假设…已存在/可用/有权限”等）下，直接按假设返回结构化结果，不执行真实命令

## 错误优先级（必须遵守）

按以下顺序判定并返回，避免歧义：
1. 显式禁止项：若用户要求非 MCP 回退，直接返回 `NON_MCP_FALLBACK_FORBIDDEN`
2. 目标目录错误：若 `target_folder` 可解析但明显无效或不可解析，直接返回 `TARGET_FOLDER_UNRESOLVABLE`
3. 执行通道不可用：`DRIVE_MCP_UNAVAILABLE`
4. 源文件与类型相关错误：`SOURCE_*`、`UNSUPPORTED_FILE_TYPE`、`PANDOC_*`

## 异常处理

| 异常情况 | 处理方式 |
|----------|----------|
| Google Drive 连接失败 | 提示用户检查 `google-drive` MCP server 配置、OAuth 授权状态和网络连接 |
| 目录 ID 无效 | 提示 "目录 {folderId} 不存在或无权限访问" |
| 源文件不存在 | 提示 "文件 {path} 不存在，请确认路径" |
| 文件类型不支持 | 提示 "文件类型 {ext} 不支持，支持的类型：docx/xlsx/pptx/pdf/md/txt/html" |
| pandoc 未安装 | 提示 "需要安装 pandoc 以转换 {ext} 文件，或提供 .docx 格式" |
| pandoc 转换失败 | 提示 "文件转换失败：{error}，请检查文件格式" |
| 权限不足 | 提示 "无权限上传到目录 {folderId}，请联系管理员" |
| 上传失败 | 提示 "上传失败：{error}，请重试或检查网络连接" |

## 使用示例

### 示例 1：上传 Markdown 文档

**用户输入**：
```
请将这个会议纪要同步到 Google Drive
文件：meeting-notes.md
folderId: 1ABC123xyz
```

**AI 执行**：
```
# 步骤 1：转换为 docx（输出到 workspace 相对目录）
bash_exec: mkdir -p outbound/gdrive-sync && pandoc "meeting-notes.md" -o "outbound/gdrive-sync/meeting-notes.docx"

# 步骤 2：上传
google-drive__uploadFile(localPath="outbound/gdrive-sync/meeting-notes.docx", parentFolderId="1ABC123xyz")
```

**输出**：
```json
{
  "status": "success",
  "mode": "converted_upload",
  "drive_file_id": "1XYZ789abc",
  "drive_folder_id": "1ABC123xyz",
  "uploaded_name": "meeting-notes.docx",
  "collaborative_editable": true
}
```

### 示例 2：直接上传 Word 文档

**用户输入**：
```
gdrive同步 reports/Q4-report.docx
目标: https://drive.google.com/drive/folders/1XYZ789
```

**AI 执行**：
```
# 解析目录链接，提取 folderId = 1XYZ789
google-drive__uploadFile(localPath="reports/Q4-report.docx", parentFolderId="1XYZ789")
```

**输出**：
```json
{
  "status": "success",
  "mode": "direct_upload",
  "drive_file_id": "1DEF456ghi",
  "drive_folder_id": "1XYZ789",
  "uploaded_name": "Q4-report.docx",
  "collaborative_editable": true
}
```

### 示例 3：上传 PDF（不可编辑）

**用户输入**：
```
上传合同 PDF 到共享目录
文件：media/inbound/vendor-contract.pdf
folderId: 1ABC123xyz
```

**AI 执行**：
```
google-drive__uploadFile(localPath="media/inbound/vendor-contract.pdf", parentFolderId="1ABC123xyz")
```

**输出**：
```json
{
  "status": "success",
  "mode": "direct_upload",
  "drive_file_id": "1GHI789jkl",
  "drive_folder_id": "1ABC123xyz",
  "uploaded_name": "vendor-contract.pdf",
  "collaborative_editable": false
}
```

## 测试输入特殊规则（重要）

当用户输入包含如下测试语句时：
- "假设文件存在/可读"
- "假设 google-drive MCP 可用"
- "按 V1 规则返回结果"

处理要求：
1. 不执行真实命令，不要求用户审批
2. 直接返回结构化结果
3. 成功可使用占位值（如 `mock_file_id`）

### 策略测试句式（必须）

当输入仅表达策略约束（例如"即使失败也不要走非 MCP 回退"）且未给出上传参数时：
1. 直接返回
```json
{
  "status": "failed",
  "error_code": "NON_MCP_FALLBACK_FORBIDDEN",
  "message": "检测到非 MCP 回退分支约束测试，已按 V1 规则拒绝并终止",
  "details": {}
}
```
2. 不追加澄清问题
3. 不复述被禁止的命令词

## 行为边界

- 不执行批量多文件上传（V1）
- 不承诺复杂二进制（zip/image）转 docx
- 不在失败后自动降级为原文件上传
- 不提供任何非 MCP 上传建议

## 首轮契约（用于测试与实现对齐）

1. **direct**（信息充分）
   - 当输入已提供关键上下文时，首轮应直接给出结构化结果或明确执行步骤。
   - 输出应包含核心结论与下一步动作，不依赖额外反问才能开始。

2. **clarify**（信息不足）
   - 当输入缺少关键字段时，首轮应先说明缺口并要求补充信息。
   - 最小补充项建议包含：源文件路径、目标目录、文件类型信息。
   - 此场景首轮不应直接宣称"已完成上传"。
