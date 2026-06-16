---
name: common-email-template-scan
description: 扫描 Google Drive 邮件模版文件夹，列出所有模版文件清单（含 fileId）。不执行转换、不比对本地状态，以线上模版为准。触发词：扫描邮件模版、scan email templates、邮件模版扫描、查看邮件模版
status: active
metadata:
  author: RD Team
  version: 2.1.0
---

# 邮件模版扫描 Skill

> **输出规则（必须遵守）**：
> 本 skill 向用户发送的消息**只允许包含「完成输出」章节中定义的扫描结果**，禁止包含工具调用内容、中间过程描述等。
>
> 正确做法：静默执行所有步骤，完成后向用户发送**一条消息**，内容仅为扫描结果。

## 概述

从 Google Drive 拉取邮件模版文件夹的文件列表，按过滤规则筛选，输出所有模版的名称和 fileId。

**本 skill 单一职责：GDrive 目录快照。** 不读本地状态、不比对 md5、不判断哪些文件需要转换——那是 `common-email-template-sync` 的职责。

扫描结果写入本地 `${SANDBOX_MEDIA_DIR}/email-template-sync/scan-result.json`，供编排脚本或用户逐个调用 sync 使用。

## 前置条件

- `google-drive` MCP server 已挂载（fleetent MCP 工具直接按名调用）
- 沙箱 env 中已注入 `GDRIVE_EMAIL_TEMPLATE_FOLDER`

---

## 工作流

### Step 1 — Preflight

用 `bash_exec` 读取：
```bash
echo $GDRIVE_EMAIL_TEMPLATE_FOLDER
```

若为空，终止并输出：
```
❌ 未配置 GDRIVE_EMAIL_TEMPLATE_FOLDER 环境变量。
   请在沙箱 env 中注入该变量后重试。
```

### Step 2 — 从 Google Drive 拉取文件列表

调用 `google-drive__listFolder` 工具，`folderId` 传 Step 1 读取到的 `GDRIVE_EMAIL_TEMPLATE_FOLDER` 值。

**GDrive 连接失败处理**：调用 `google-drive__listFolder` 报错时，重试一次；仍失败 → 终止并输出：
```
❌ GDrive 不可用，请检查 google-drive MCP server 是否正常挂载。
```

**过滤规则**（对 listFolder 返回的每个文件逐一检查）：
- ✓ 保留：扩展名为 `.docx` 的文件（原始模版）
- ✗ 跳过：Google Doc 文件（mimeType 为 `application/vnd.google-apps.document`，这是 sync 产出的转换文件）
- ✗ 跳过：文件名匹配 `*-YYYYMMDD_HHmmss.docx` 模式（8 位日期 + 6 位时间的导出产物）
- ✗ 跳过：文件名以 `-converted.docx` 结尾（反编译产物）
- ✗ 跳过：文件名以 `-template.docx` 结尾（sync 上传前的临时 docx）

若 listFolder 返回为空，终止并提示：
```
❌ GDrive 文件夹为空或文件夹 ID 有误，请检查 GDRIVE_EMAIL_TEMPLATE_FOLDER 的值。
```

### Step 3 — 写出 scan-result.json + 完成输出

根据过滤结果，用 `run_code`（沙箱内 Python）执行以下脚本（将占位符替换为真实数据后执行）：

```python
import json, os
results = [
  {'name': '模版名1', 'fileId': 'fileId1'},
  {'name': '模版名2', 'fileId': 'fileId2'},
]
sandbox_media_dir = os.environ['SANDBOX_MEDIA_DIR']
os.makedirs(f'{sandbox_media_dir}/email-template-sync', exist_ok=True)
with open(f'{sandbox_media_dir}/email-template-sync/scan-result.json', 'w', encoding='utf-8') as f:
    json.dump(results, f, ensure_ascii=False, indent=2)
print('OK')
```

- `name`：文件名去掉 `.docx` 后缀的模版名
- `fileId`：listFolder 返回的文件 id 字段
- 若过滤后无文件，`results` 为空列表 `[]`

### 完成输出

```
📋 邮件模版扫描结果（{扫描时间}）：

共 {N} 个模版：
  1. 【通用】地址创建申请 模版
  2. 【通用】子账户申请模版
  ...

💾 结构化结果：${SANDBOX_MEDIA_DIR}/email-template-sync/scan-result.json
💡 同步单个模版：同步邮件模版 【通用】地址创建申请 模版
💡 批量同步（编排脚本）：python3 orchestrate_email_sync.py
```

若过滤后无文件：
```
📋 邮件模版扫描结果（{扫描时间}）：

⚠️ 过滤后无可用模版文件，请检查 GDrive 文件夹内容。
💾 结构化结果：${SANDBOX_MEDIA_DIR}/email-template-sync/scan-result.json（空数组）
```

## 错误处理

| 错误情况 | 处理方式 |
|----------|----------|
| `$GDRIVE_EMAIL_TEMPLATE_FOLDER` 未配置 | 输出配置指南，终止 |
| GDrive 连接失败 | 重试 `google-drive__listFolder` 一次 → 仍失败则终止，提示检查 google-drive MCP server 挂载状态 |
| listFolder 返回为空 | 提示检查文件夹 ID，终止 |
| 过滤后无 .docx 文件 | 写空数组 `[]`，输出警告，正常退出 |
