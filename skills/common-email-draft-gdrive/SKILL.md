---
name: common-email-draft-gdrive
description: 基于 Google Drive 上的 Google Doc 邮件模版进行邮件起草（只读）。从 GDrive 实时拉取模版列表，直接读取模版内容提取占位符，本 skill 不允许修改模版。触发词：起草邮件、draft email、gdrive邮件、邮件起草、选择邮件模版
status: active
metadata:
  author: RD Team
  version: 4.0.0
---

# 邮件起草 GDrive Skill

## ⚠️ 关键约束

1. **严禁修改模版** — 本 skill 仅读取模版用于起草邮件，不得编辑、写回、上传任何文件
2. **脚本错误立即停止** — 脚本 exit non-zero 时，将 stderr 内容直接告知用户，不尝试绕过
3. **邮件输出必须可直接复制粘贴** — 纯文本，不使用 markdown 代码块，不添加说明性文字
4. **占位符必须全部替换** — 不得在输出中留有 `{xxx}` 未替换内容

若用户要求修改模版，引导使用 `common-email-template-sync` skill。

## 前置条件

- `google-drive` MCP server 已挂载（fleetent MCP 工具直接按名调用）
- 环境变量已配置：`GDRIVE_EMAIL_TEMPLATE_FOLDER`

## 执行流程

### Step 1 — 列出可用模板

调用 `google-drive__listFolder` 工具，`folderId` 传 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 的值，列出模板文件夹下的文件。从返回结果中筛出名称以 `-AI` 结尾的 Google Doc 模板，提取每个模板的名称（去掉 `-AI` 后缀）和 `file_id`。

> 注：原 `scripts/list-templates.sh` 通过 `mcpfast` 在 shell 内调用 MCP；fleetent 的 MCP 工具是模型层直接工具调用，无法从 shell 脚本发起，因此本步骤改为直接调用 `google-drive__listFolder`，脚本不再使用。

将筛出的列表按 `<编号>. <模板名称>  <file_id>` 格式直接展示给用户，等待用户选择模板编号或名称。

### Step 2 — 读取模板内容

根据用户选择，从 Step 1 取得对应 `file_id`，调用 `google-drive__readGoogleDoc` 工具：

```
google-drive__readGoogleDoc(documentId=<file_id>, format="text")
```

读取返回的模板全文，理解模板结构，识别所有需要填写的变量（固定收件人/抄送、邮件主题格式、正文占位符等）。

### Step 3 — 收集参数

根据模板内容判断各变量的必填/可选和含义，逐一向用户收集缺失的必填参数。可选参数未提供时使用默认值或留空，不重复询问。

### Step 4 — 生成邮件草稿

将收集到的参数填入模板，按以下格式输出邮件草稿：

```
收件人：<邮箱或姓名>
抄送：<抄送列表，逗号分隔>
主题：<邮件主题>

<邮件正文>
```

输出规范：
- 直接输出纯文本，不用 markdown 代码块
- 使用中文标点（中文冒号、逗号）
- 日期格式 YYYY-MM-DD
- 不添加说明性文字（如"以下是邮件草稿："）
