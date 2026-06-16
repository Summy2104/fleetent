---
name: common-file-output
description: 文件生成、保存和发送规范。生成文件、保存文件、发送文件、发送附件、发文件、文件发送给用户时必须使用本 skill。定义统一的路径、命名和平台投递方式。触发词：file_manager、common-file-output、文件管理、保存规范、发文件、发送文件、生成文件、文件附件。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# 文件管理器

智能 workspace 文件管理规范。AI 根据内容长度自动决定是否保存文件，无需用户确认。

## 核心原则

- **智能判断**：AI 根据内容长度和文档类型自动决定是否保存
- **零交互**：不询问用户，自动处理
- **统一规范**：所有 skills 遵循相同的命名和组织标准

## 文件编码规范

**所有生成的文本文件必须使用 UTF-8 编码保存（无 BOM）。**

## 目录结构

写入路径：`outbound/{关键词}/{YYYY-MM}/{文档名}`（相对 workspace 根目录）

```
outbound/
├── user-login/              # AI 根据需求语义判断的关键词
│   └── 2026-03/
│       ├── PRD-用户登录-20260302.md
│       └── 技术方案-登录模块-20260302.md
├── payment/
│   └── 2026-03/
│       └── 代码-payment.go
└── bugfix/
    └── 2026-03/
        └── Bug报告-登录超时-20260302.md
```

**关键词**：AI 根据需求语义自动判断，如用户登录 → `user-login`，支付模块 → `payment`

## 文件命名规范

从目录结构可以看到常见的命名模式：

- `PRD-{功能名}-{YYYYMMDD}.md`
- `技术方案-{功能名}-{YYYYMMDD}.md`
- `会议纪要-{主题}-{YYYYMMDD}.md`
- `Bug报告-{问题描述}-{YYYYMMDD}.md`
- `功能文档-{模块名}-{YYYYMMDD}.md`
- `架构文档-{模块名}-{YYYYMMDD}.md`
- `研发周报-{YYYYMMDD}.md`
- `产品周报-{YYYYMMDD}.md`
- `用户反馈分析-{YYYYMMDD}.md`
- `数据洞察-{主题}-{YYYYMMDD}.md`
- `PR摘要-{YYYYMMDD}.md`
- `需求收集-{主题}-{YYYYMMDD}.md`
- `CHANGELOG-v{X.Y.Z}.md`
- `RELEASE-NOTES-v{X.Y.Z}.md`
- `分析报告-{主题}-{YYYYMMDD}.md`

表格数据命名：
- `{主题}-{YYYYMMDD}.tsv`（默认，人工可读/粘贴到 Sheets）
- `{主题}-{YYYYMMDD}.json`（程序消费）

测试代码命名：
- Go: `{模块名}_test.go`
- Python: `test_{模块名}.py`
- TypeScript/JavaScript: `{模块名}.test.ts` / `{模块名}.test.js`

## 表格数据输出规范

当 skill 需要输出结构化表格数据（非 Markdown 文档）时，按以下规则选型。

### 格式选型

| 场景 | 格式 | 理由 |
|------|------|------|
| 用户需要粘贴到 Google Sheets / Excel | **TSV** | Tab 分隔数据粘贴即自动分列，无需导入向导 |
| 审计报告、清单、对账等人工可读表格 | **TSV** | 字段含逗号时无需转义，可读性好 |
| 程序/脚本消费的结构化数据 | **JSON** | 类型保真，嵌套结构天然支持 |
| 需要前端渲染或 API 传输 | **JSON** | 标准序列化格式 |

**默认选 TSV**。只有明确是程序消费场景才用 JSON。不使用 CSV。

### TSV 格式要求

- 编码：UTF-8（无 BOM），与文本文件规范一致
- 首行为表头（字段名）
- 字段内不得包含 Tab 字符；如遇换行符，替换为空格
- 空值用空字符串表示（两个相邻 Tab）
- 文件扩展名：`.tsv`

### JSON 格式要求

- 编码：UTF-8
- 顶层为数组（每条记录一个对象）或包含 `records` 数组的对象
- 空值用 `null` 表示
- 文件扩展名：`.json`

## 保存策略

### 永远保存
`product-prd-gen` `dev-prd-tech-design-gen` `product-meeting-notes-gen` `dev-jira-issue-gen` `product-func-doc-gen` `dev-release-notes-gen` `product-changelog-gen`

### 8 行以上保存
所有其他生成型 skills

## 回复格式

### 已保存文件（附件发送）

**步骤：**
1. 写入文件到 workspace：用 `write_file` 写到相对路径
   `outbound/{关键词}/{YYYY-MM}/{文件名}.md`（相对 workspace 根目录）。
   工具会返回文件路径备用。

2. 发送附件：用内置 `send_file` 工具投递。`send_file` 会把文件投递回**当前对话**
   （在频道里触发就回频道、私信里触发就回私信），无需指定收件人或宿主机路径。
   ```
   send_file(path="outbound/{关键词}/{YYYY-MM}/{文件名}.md")
   ```

3. 聊天中只输出摘要，**不得**直接输出文件完整内容，**不得**暴露内部路径。

**聊天摘要格式：**
```
{3-5 行核心内容}
```

### 直接返回（< 8 行）
{完整内容}

## 入站图片路径（Inbound）

用户通过 Slack / Telegram 发送的图片由 fleetent gateway 投递到 agent 的 workspace。

**规则**：
- 读取用户发来的图片：按 fleetent 约定从 ToolContext 提供的附件路径取，用内置 `read_file`
  （或 `analyze_image`）读取；不要假设任何宿主机绝对路径。
- 如需将图片附件转存到 outbound，复制到 `outbound/{关键词}/{YYYY-MM}/` 并按正常文件流程
  （`write_file` → `send_file`）发送。

## 使用方式

生成型 skills 在生成内容后：

1. 判断文档类型和内容行数
2. ≥ 8 行：`write_file` 写文件 → `send_file` 发附件 → 聊天只输出摘要
3. < 8 行：直接在聊天中返回完整内容

**示例**：
- `product-prd-gen` 生成 PRD（20 行）→ 写到 outbound/ → 用 `send_file` 投递附件
- `dev-bug-analyze` 分析错误（5 行）→ 直接返回
