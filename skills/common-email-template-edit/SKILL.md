---
name: common-email-template-edit
description: 修改 Google Drive 上已转换的 -AI Google Doc 邮件模版。下载为 markdown → AI 按用户指令修改 → 重新上传为 Google Doc。读取 common-email-template-sync 的转换规则确保修改后内容符合规范。触发词：修改邮件模版、编辑邮件模版、edit email template、更新邮件模版
status: active
metadata:
  author: RD Team
  version: 2.0.0
---

# 邮件模版编辑 Skill

> **输出规则（必须遵守）**：
> 本 skill 向用户发送的消息**只允许包含「完成输出」章节中定义的结果摘要**，禁止包含以下任何内容：
> - 正在执行哪个步骤（如"Step 1"、"Step 3"）
> - exec 命令的内容或返回结果
> - 文档读取、下载、转换、编辑操作的过程描述
> - "开始编辑"、"正在下载"、"正在转换"等进度说明
>
> 正确做法：静默执行所有步骤，完成后向用户发送**一条消息**，内容仅为结果摘要。

> **执行约束（强制，违反即失败）**：
> 1. **只编辑 `-AI` Google Doc** — 不得修改 `.docx` 原始模版，不得创建新文件（除工作目录中的临时文件）。
> 2. **每次只修改一个模版** — 用户必须指定模版名称，不支持批量编辑。
> 3. **文件路径必须加引号** — 文件名可能包含 `&`、空格、括号等 shell 特殊字符，所有 `bash_exec` 命令中涉及文件名的路径**必须用引号包裹**。
> 4. **文件夹范围内定位** — 定位 `-AI` 文档必须在 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 文件夹内匹配，禁止跨文件夹或全局搜索。
> 5. **禁止使用 `updateGoogleDoc`** — 全量替换会丢失所有格式。
> 6. **禁止使用 Google Docs API 精确编辑工具**（`findAndReplaceInDoc`、`insertText`、`deleteRange`、`editTableCell`）— 无法可靠处理表格结构变更，统一走下载-修改-上传重建流程。

## 概述

修改 Google Drive 上已转换的 `-AI` Google Doc 邮件模版：

- 用户通过对话描述修改意图（如"把开户申请模版的抄送加上 legal@nsdigital.io"、"在正文表格中新增审批人字段"）
- Agent 下载 `-AI` 文档为 markdown → 按用户指令修改 → 重新上传为 Google Doc
- 读取 `common-email-template-sync` 的转换规则（`CONVERSION_RULES.md` + `conversion-config.yaml`）确保修改后内容符合规范
- 编辑完成后更新 `sync-state` 和 `template-index.json`，反馈结果 + 文档在线链接

本 skill 与 `common-email-template-sync` 独立互不干扰，但共享状态文件。

## 前置条件

- `google-drive` MCP server 已挂载（fleetent MCP 工具直接按名调用）
- 沙箱内已安装 pandoc（`which pandoc` 可找到）
- 已配置 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 环境变量
- 目标模版已通过 `common-email-template-sync` 生成对应的 `-AI` Google Doc

## 环境变量

沙箱 env 中已注入以下变量（用 `bash_exec` 读取）：

```bash
# GDrive 文件夹 ID
echo $GDRIVE_EMAIL_TEMPLATE_FOLDER

# 工作区媒体目录
echo $SANDBOX_MEDIA_DIR
```

> 脚本/转换规则文件位于本 skill 目录下，由 runtime 注入的绝对位置解析后使用。

## 本地工作目录

```
${SANDBOX_MEDIA_DIR}/email-template-edit/
└── *.docx / *.md    ← 下载/转换的临时文件（每次编辑完成后清理，不留存）

${SANDBOX_MEDIA_DIR}/email-template-sync/
├── sync-state/{name}.json    ← 更新 doc_file_id（与 sync 共享）
└── template-index.json       ← 更新 doc_file_id（与 sync 共享）
```

> **注意**：`email-template-edit/` 目录仅存放当次编辑的临时文件，Step 8 会清理。不要读取该目录下的历史文件作为模版内容来源。

---

## 工作流

**触发词**：`修改邮件模版`、`编辑邮件模版`、`edit email template`、`更新邮件模版`

### Step 1 — Preflight & 输入解析

用 `bash_exec` 读取：
```bash
echo $GDRIVE_EMAIL_TEMPLATE_FOLDER
```

若为空，终止并输出：
```
❌ 未配置 GDRIVE_EMAIL_TEMPLATE_FOLDER 环境变量。
   请在沙箱 env 中注入该变量后重试。
```

从用户消息中提取：
- **模版名**（必填）：模糊匹配，如"修改开户申请模版的收件人"中提取"开户申请"
- **修改意图**（必填）：用户想改什么，如"把抄送加上 legal@nsdigital.io"

若未指定模版名，终止并输出：
```
❌ 请指定模版名称，例如：修改邮件模版 【通用】地址创建申请 模版 把抄送加上 legal@nsdigital.io
💡 使用「扫描邮件模版」查看可用模版列表。
```

若修改意图不明确，向用户追问具体要改什么。

### Step 2 — 定位目标 `-AI` Google Doc

**优先路径（本地索引存在）**：
```bash
cat "${SANDBOX_MEDIA_DIR}/email-template-sync/template-index.json"
```

按模版名模糊匹配，取 `doc_file_id`（即 `-AI` Google Doc 的 fileId）。

**Fallback 路径（本地索引不存在或未命中）**：调用 `google-drive__listFolder` 工具，`folderId` 传 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 的值。

从结果中按 `{name}-AI` 名称匹配 mimeType 为 `application/vnd.google-apps.document` 的 Google Doc，取其 fileId。

**GDrive 连接失败处理**：调用 `google-drive__listFolder` 报错时，重试一次；仍失败 → 终止并输出：
```
❌ GDrive 不可用，请检查 google-drive MCP server 是否正常挂载。
```

若找不到对应 `-AI` 文档，终止：
```
❌ 未找到模版：{name} 的 -AI 文档
   请先运行「同步邮件模版 {name}」生成对应的 Google Doc。
```

### Step 3 — 下载 `-AI` Google Doc 并转换为 markdown

**Step 3.1 — 下载 Google Doc（导出为 docx）**

先用 `bash_exec` 建目录：
```bash
mkdir -p "${SANDBOX_MEDIA_DIR}/email-template-edit"
```

再调用 `google-drive__downloadFile` 工具下载并导出为 docx：
```
google-drive__downloadFile(
  fileId="{doc_file_id}",
  localPath="${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-AI.docx",
  exportMimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)
```

若下载失败（连接错误），执行 Step 2 中的「GDrive 连接失败处理」流程，重试一次。

**Step 3.2 — pandoc 转换为 markdown**（用 `bash_exec`）

```bash
pandoc "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-AI.docx" \
  -f docx -t markdown --wrap=none \
  -o "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}.md"
```

### Step 4 — 读取转换规则

用 `read_file` 读取 `common-email-template-sync` skill 目录下的转换规则文件（runtime 注入的绝对位置解析）：

```
read_file: <common-email-template-sync skill 目录>/conversion-config.yaml
read_file: <common-email-template-sync skill 目录>/CONVERSION_RULES.md
```

若规则文件不存在，仅凭 markdown 内容和用户指令进行修改（不做规范性校验），继续执行。

### Step 5 — AI 按用户指令修改 markdown

读取 `{name}.md` 内容（用 `read_file` 或 `bash_exec` cat）：
```bash
cat "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}.md"
```

结合以下信息执行修改：
- 用户的修改指令
- `conversion-config.yaml` 中的数据（fixed_roles、placeholders、subject_labels 等）
- `CONVERSION_RULES.md` 中的输出规范（四段式结构）

**修改后必须确保**：
- 仍遵守四段式结构（📋 基本信息 / 📥 收件人信息 / 📤 邮件正文 / 💡 使用指南）
- 占位符命名遵守 `conversion-config.yaml` 的规范（小写字母 + 下划线，优先复用已有占位符）
- 固定角色（在 `fixed_roles` 中）仍使用邮箱地址而非占位符
- 新增占位符需同步添加到「💡 使用指南 → 变量替换说明表」
- 删除占位符需同步从变量替换说明表中移除

将修改后的 markdown 写入（用 `write_file`，或 `bash_exec` heredoc）：
```bash
cat > "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-edited.md" << 'EDITEOF'
{修改后的完整 markdown 内容}
EDITEOF
```

### Step 6 — 转换为 docx 并上传为 Google Doc

**Step 6.1 — pandoc 转 docx**（用 `bash_exec`）：
```bash
pandoc "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-edited.md" \
  -f markdown -t docx \
  -o "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-template.docx"
```

**Step 6.2 — 删除旧 `-AI` Google Doc**：调用 `google-drive__deleteItem` 工具：
```
google-drive__deleteItem(itemId="{doc_file_id}")
```

**Step 6.3 — 上传新 docx 并转为 Google Doc**（文件名保持 `-AI` 后缀）：调用 `google-drive__uploadFile` 工具：
```
google-drive__uploadFile(
  localPath="${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-template.docx",
  name="{name}-AI",
  parentFolderId="{FOLDER_ID}",
  mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  convertToGoogleFormat=true
)
```
记录返回的 `id`（即新的 `doc_file_id`）。

### Step 7 — 更新状态文件

**更新 sync-state**（仅本地，用 `bash_exec`）：
```bash
mkdir -p "${SANDBOX_MEDIA_DIR}/email-template-sync/sync-state"
cat > "${SANDBOX_MEDIA_DIR}/email-template-sync/sync-state/{name}.json" << 'STATEEOF'
{
  "file_name": "{name}.docx",
  "md5": "{current_md5}",
  "gdrive_file_id": "{原始docxFileId}",
  "doc_file_id": "{新doc_file_id}",
  "last_converted": "{ISO8601时间戳}"
}
STATEEOF
```

**更新 template-index.json**（仅本地，merge 模式，用 `run_code` 运行 Python）：
```python
import json
from pathlib import Path

index_path = Path('${SANDBOX_MEDIA_DIR}/email-template-sync/template-index.json')
index = {}
if index_path.exists():
    index = json.loads(index_path.read_text(encoding='utf-8'))

index['{name}']['doc_file_id'] = '{新doc_file_id}'
index['{name}']['last_converted'] = '{ISO8601时间戳}'

index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
print('OK')
```

### Step 8 — 清理临时文件

上传完成后，**必须删除本次产生的所有中间转换文件**，防止 AI 在后续对话中误读旧文件内容（用 `bash_exec`）：

```bash
rm -f "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-AI.docx" \
            "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}.md" \
            "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-edited.md" \
            "${SANDBOX_MEDIA_DIR}/email-template-edit/{name}-template.docx"
```

> **为什么必须清理**：中间文件（特别是 `.md` 文件）包含修改前/修改后的模版内容。若不清理，后续对话中 AI 可能读取到这些本地文件并误以为是最新模版，导致基于过期内容做出错误判断或修改。每次编辑都应从 GDrive 线上拉取最新版本。

### 完成输出

```
✅ 模版已修改：{name}
   📝 修改内容：{修改摘要，如"邮件正文新增审批人字段，使用指南同步更新"}
   🔗 查看文档：https://docs.google.com/document/d/{新doc_file_id}/edit
```

## 错误处理

| 错误情况 | 处理方式 |
|----------|----------|
| `$GDRIVE_EMAIL_TEMPLATE_FOLDER` 未配置 | 输出配置指南，终止 |
| 未指定模版名 | 提示指定名称，建议先用 `common-email-template-scan` 查看列表 |
| 模版名找不到对应 `-AI` 文档 | 提示先运行 `common-email-template-sync` 同步该模版 |
| 修改意图不明确 | 向用户追问具体要改什么 |
| GDrive 连接失败 | 重试 `google-drive__listFolder` 一次 → 仍失败终止，提示检查 google-drive MCP server 挂载状态 |
| pandoc 未安装 | 提示安装，终止 |
| pandoc 转换失败 | 输出错误信息，终止，本地文件已保留 |
| 上传失败 | 输出错误信息，本地文件已保留 |
| 删除旧文件失败 | 输出警告，跳过删除继续上传（可能导致文件夹中存在两个 -AI 文档）|
