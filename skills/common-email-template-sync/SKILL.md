---
name: common-email-template-sync
description: 同步指定的单个邮件模版：从 Google Drive 下载 docx，转换为结构化 markdown（pandoc + AI 语义转换），上传为 Google Doc。每次只处理一个模版。触发词：同步邮件模版、sync email template、强制同步邮件模版、force sync email template
status: active
metadata:
  author: RD Team
  version: 5.1.0
---

# 邮件模版同步 Skill（单文档处理）

> **输出规则（必须遵守）**：
> 本 skill 向用户发送的消息**只允许包含「完成输出」章节中定义的结果摘要**，禁止包含以下任何内容：
> - 正在执行哪个步骤（如"Step 1"、"Step B5"）
> - 工具调用（bash_exec / run_code / google-drive MCP 等）的内容或返回结果
> - 文件下载、pandoc 转换、语义转换的过程描述
> - "开始同步"、"正在读取"等进度说明
>
> 正确做法：静默执行所有步骤，完成后向用户发送**一条消息**，内容仅为结果摘要。

> **执行约束（强制，违反即失败）**：
> 1. **每次调用只处理一个模版文档**：用户必须指定模版名称。不得循环、批量、并行处理多个文件。不得使用 sub_agent。
> 2. **文件路径必须加引号**：文件名可能包含 `&`、空格、括号等 shell 特殊字符，所有 `bash_exec` 命令中涉及文件名的路径**必须用引号包裹**。
> 3. **违反上述任一条即视为转换失败**。

## 概述

将 Google Drive 上**指定的单个** docx 邮件模版转换为结构化 markdown，再转为 Google Doc 存回同一 Google Drive 文件夹。最终产出为 Google Doc 格式，支持在线编辑和查看。

每次调用只处理一个模版，确保规则始终在上下文最近位置，100% 遵从。如需批量同步，先使用 `common-email-template-scan` skill 扫描全量清单，再通过编排脚本逐个调用本 skill。

转换分两步：
1. **pandoc 格式转换**：docx → 原始 markdown
2. **AI 语义转换**：按规则文件将原始 markdown 转为四段式结构化模版

支持两种模式：
- **普通同步**（`同步邮件模版 {模版名}`）：md5 无变化则跳过
- **强制同步**（`强制同步邮件模版 {模版名}`）：忽略 md5，强制重新转换

支持两种输入方式：
- **仅模版名**（`同步邮件模版 {模版名}`）：自动调用 listFolder 定位文件
- **模版名 + fileId**（`同步邮件模版 {模版名} --file-id {fileId}`）：直接使用 fileId，跳过 listFolder

## 前置条件

- `google-drive` MCP server 已挂载并完成 OAuth 授权（工具名 `google-drive__*`）
- 已安装 pandoc（`which pandoc` 可找到）
- 环境变量 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 已配置（目标 Google Drive 文件夹 ID）

## 规则文件

规则文件放在本 skill 目录下的 per-agent 子目录（`{agent-id}` 为当前 agent 名）：

```
skills/common-email-template-sync/{agent-id}/
├── conversion-config.yaml    ← 结构化数据：固定角色、占位符库、主题标签、审批模式
└── CONVERSION_RULES.md       ← 转换指令：三阶段流水线（清理 → 语义识别 → 结构化输出）
```

> 用 `read_skill` 或 `read_file` 读取这两个规则文件。

**conversion-config.yaml** 提供精确数据（机器可读）：
- `fixed_roles`：固定角色清单（个人 + 业务线专属 + 群组邮箱）
- `placeholders`：标准占位符库（命名规范，优先复用）
- `subject_labels`：邮件主题标签
- `approval_patterns`：审批流程模式
- `custom_rules`：用户自定义规则

**CONVERSION_RULES.md** 提供转换指令（人类可读可编辑）：
- 阶段一：清理 pandoc 格式残留（`{.mark}`、转义字符、HTML 表格等）
- 阶段二：语义识别（固定角色 vs 占位符、可变内容、主题、审批、表格、多模版）
- 阶段三：结构化输出（四段式：📋 基本信息 / 📥 收件人信息 / 📤 邮件正文 / 💡 使用指南）

## Google Drive 文件夹结构

```
{agent-gdrive-folder}/
├── 【通用】地址创建申请 模版.docx            ← 原始模版（永不修改）
├── 【通用】地址创建申请 模版-AI              ← 转换产出（Google Doc 格式，支持在线编辑）
（注：sync-state 仅保存在本地，不上传 GDrive）
```

## 本地工作目录

所有本地文件用 workspace 相对路径，统一放在 `media/email-template-sync/`：

```
media/email-template-sync/
├── sync-state/                ← 状态目录（每个模版一个独立文件，仅本地）
│   ├── 【通用】地址创建申请 模版.json
│   └── ...
├── template-index.json        ← 模版索引（供 common-email-draft-gdrive 使用，仅本地）
└── *.docx / *-raw.md / *.md   ← 转换临时文件
```

---

## 工作流

### Step 1 — Preflight & 输入解析

```
bash_exec: echo $GDRIVE_EMAIL_TEMPLATE_FOLDER
```

若为空，终止并输出错误提示。

从用户消息中提取：
- **模版名**（必填，去掉 `.docx` 后缀，模糊匹配）。若未指定，输出错误并终止：
  ```
  ❌ 请指定模版名称，例如：同步邮件模版 【通用】地址创建申请 模版
  💡 使用「扫描邮件模版」查看可用模版列表。
  ```
- **fileId**（可选）：消息中包含 `--file-id {value}` 时提取该值，否则为空
- **强制模式**：消息包含「强制」或「force」时为 true

### Step 2 — 读取规则文件

用 `read_file` 读取本 skill 目录下当前 agent 的规则文件：

```
read_file: skills/common-email-template-sync/{agent-id}/conversion-config.yaml
read_file: skills/common-email-template-sync/{agent-id}/CONVERSION_RULES.md
```

若规则文件不存在，标记为「仅格式转换模式」（跳过 Step 6 语义转换），继续执行。

### Step 3 — 定位目标文件

**有 fileId**（Step 1 已提取）→ 直接使用该 fileId，跳过 listFolder。

**无 fileId** → 调用 listFolder 查找：
```
google-drive__listFolder(folderId="<GDRIVE_EMAIL_TEMPLATE_FOLDER值>")
```

**GDrive 连接失败处理**（仅在无 fileId 调用 listFolder 时适用）：
1. 重试 listFolder 一次
2. 重试仍失败 → 终止并输出：
   ```
   ❌ GDrive 不可用：google-drive MCP server 无法连接。
      请检查 google-drive MCP server 配置与 OAuth 授权状态。
   ```

从 listFolder 结果中按模版名模糊匹配 `.docx` 文件。若找不到，终止：
```
❌ 未找到模版：{name}
   请使用「扫描邮件模版」确认可用模版列表后重试。
```

同时从 listFolder 结果或 sync-state 记录中获取：
- 旧 Google Doc 的 fileId（`old_doc_file_id`，按 `{name}-AI` 名称匹配，若存在）

### Step 4 — 下载 docx & md5 检查

```
bash_exec: mkdir -p media/email-template-sync
google-drive__downloadFile(fileId="{docxFileId}", localPath="media/email-template-sync/{name}.docx")
bash_exec: md5sum "media/email-template-sync/{name}.docx"
```

读取当前模版的状态文件（若存在）：
```
bash_exec: mkdir -p media/email-template-sync/sync-state
read_file: media/email-template-sync/sync-state/{name}.json
```

记录 `md5sum` 输出的哈希值为 `current_md5`。

**非强制模式**：若 `current_md5` 与状态文件中的 `md5` 字段相同，输出跳过提示并终止：
```
⏭️ 模版无变化，跳过：{name}（md5 一致）
```
**强制模式**：忽略 md5 比较，继续执行。

### Step 5 — pandoc 格式转换

```
bash_exec: pandoc "media/email-template-sync/{name}.docx" \
  -f docx -t markdown --wrap=none \
  -o "media/email-template-sync/{name}-raw.md"
```

产出 `{name}-raw.md`（原始 pandoc 输出，含格式残留）。

### Step 6 — AI 语义转换

按 CONVERSION_RULES.md 的三阶段流水线处理 `{name}-raw.md`：

**阶段一：清理 pandoc 格式残留**
- `[文本]{.mark}` / `[文本]{.underline}` → 保留文本，删除标记
- `[[email]{.underline}](mailto:email)` → 简化为 `email`
- `\@`, `\<`, `\>`, `\[`, `\]` → 还原原始字符
- `![](media/image*.png){...}` → `[附截图]`
- HTML 表格 → markdown 表格

**阶段二：语义识别**
结合 `conversion-config.yaml` 中的数据，逐项处理：
1. **收件人/抄送**：在 fixed_roles 中或有具体邮箱 → 仅保留邮箱地址，去掉姓名；仅有角色描述无邮箱 → 转为占位符
2. **正文可变内容**：`XX`/`xx`/方括号描述/冒号后空白 → `{placeholder}`
3. **邮件主题**：匹配 `subject_labels`
4. **审批流程**：固定审批人保留原名，可变转占位符
5. **表格**：待填写转字段列表；有数据保留 markdown
6. **多模版文件**：用二级标题区分，每个子模版独立四段结构
7. **AI 操作提示**：保留到「使用指南 → 注意事项」

**阶段三：结构化输出**
组装为四段式：📋 基本信息 / 📥 收件人信息 / 📤 邮件正文 / 💡 使用指南

转换结果写入 `media/email-template-sync/{name}.md`（用 `write_file`）。

若规则文件不存在（仅格式转换模式），直接将 `{name}-raw.md` 复制为 `{name}.md`。

### Step 7 — 转换为 docx 并上传为 Google Doc

**Step 7.1 — 将结构化 markdown 转为 docx**（保留表格格式）：
```
bash_exec: pandoc "media/email-template-sync/{name}.md" \
  -f markdown -t docx \
  -o "media/email-template-sync/{name}-template.docx"
```

**Step 7.2 — 上传到 GDrive**

**若旧 Google Doc 存在**（`old_doc_file_id` 非空）→ 先删除旧文件再上传新文件：
```
google-drive__deleteItem(itemId="{old_doc_file_id}")
```

**上传 docx 并转为 Google Doc**（文件名加 `-AI` 后缀）：
```
google-drive__uploadFile(
  localPath="media/email-template-sync/{name}-template.docx",
  name="{name}-AI",
  parentFolderId="{FOLDER_ID}",
  mimeType="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  convertToGoogleFormat=true
)
```
记录返回的 `id`（即 `doc_file_id`）。

### Step 8 — 更新状态文件（仅本地）

将当前模版的状态写入独立文件（不上传 GDrive），用 `write_file` 写入
`media/email-template-sync/sync-state/{name}.json`，内容为：

```json
{
  "file_name": "{name}.docx",
  "md5": "{current_md5}",
  "gdrive_file_id": "{docxFileId}",
  "doc_file_id": "{doc_file_id}",
  "last_converted": "{ISO8601时间戳}"
}
```

### Step 9 — 更新 template-index.json（仅本地，merge 模式）

读取现有索引文件（若存在），更新当前模版条目后写回，**不覆盖其他模版的条目**：

```
run_code:
import json
from pathlib import Path

index_path = Path("media/email-template-sync/template-index.json")
index = {}
if index_path.exists():
    index = json.loads(index_path.read_text(encoding='utf-8'))

index['{name}'] = {
    'display_name': '{display_name}',
    'gdrive_file_id': '{docxFileId}',
    'doc_file_id': '{doc_file_id}',
    'last_converted': '{ISO8601时间戳}'
}

index_path.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding='utf-8')
print('OK')
```

`display_name`：从 `{name}.md` 的第一个一级标题（`# 标题`）提取，若无则使用文件名。

### 完成输出

```
✅ 模版同步完成：{name}
   📄 已上传为 Google Doc（支持在线编辑）
   📊 sync-state/{name}.json 已更新
```

若模版无变化跳过：
```
⏭️ 跳过：{name}（md5 一致，无变化）
```

---

## 规则更新

当用户提供新规则时（如"某角色应该是固定的"、"新增转换规则"），执行以下步骤：

### Step R1 — 识别规则类型

| 规则内容 | 写入目标 |
|----------|----------|
| 固定角色 | `conversion-config.yaml` → `fixed_roles` |
| 占位符命名 | `conversion-config.yaml` → `placeholders` |
| 主题标签 | `conversion-config.yaml` → `subject_labels` |
| 自然语言规则 | `CONVERSION_RULES.md` → `用户自定义规则` 区域 |

### Step R2 — 更新规则文件

```
skills/common-email-template-sync/{agent-id}/conversion-config.yaml
skills/common-email-template-sync/{agent-id}/CONVERSION_RULES.md
```

用 `edit_file` 直接编辑对应文件的对应字段。

### Step R3 — 强制重新转换

规则更新后，**必须由用户指定需要重新转换的模版名称**：

若用户未指定具体模版名，**不执行转换**，仅提示：
```
✅ 规则已更新。请指定需要重新转换的模版名称，例如：
   强制同步邮件模版 【通用】地址创建申请 模版
```

## 错误处理

| 错误情况 | 处理方式 |
|----------|----------|
| env var 未配置 | 输出配置指南，终止 |
| 未指定模版名 | 提示指定名称，建议先扫描 |
| fileId 无效或文件不存在 | 有 fileId：报错终止；无 fileId：通过 listFolder 重新查找 |
| 规则文件不存在 | 降级为仅格式转换（跳过语义转换），正常完成 |
| GDrive 连接失败 | 重试 listFolder 一次 → 仍失败终止，提示检查 google-drive MCP server 配置与 OAuth 授权 |
| pandoc 未安装 | 提示安装，终止 |
| pandoc 转换失败 | 输出错误信息，终止，本地文件已保留 |
| AI 语义转换异常 | 上传原始 markdown 作为 fallback，输出警告 |
| 上传失败 | 输出错误信息，本地文件已保留 |
