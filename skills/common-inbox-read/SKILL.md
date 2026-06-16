---
name: common-inbox-read
description: 读取 agent 自己邮箱的收件箱。支持列出/搜索邮件（按发件人、主题、时间范围、已读/星标状态过滤）、读取邮件全文、下载邮件附件。只读，不发送、不删除。多账号时先问用户看哪个邮箱，单账号直接使用。触发词：看邮件、查收件箱、看收件箱、最近收到的邮件、读邮件、有没有人回邮件、有没有回复、检查邮箱、check inbox、查邮件、搜邮件、下载附件、邮件附件
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# 收件箱读取

让 agent 读自己的邮箱：列收件箱、按条件搜索、读全文、下载附件。**纯只读能力**——本 skill 不发送、不删除、不修改任何邮件。发信请用 `hr-recruiting-interview-invitation` 等发送类 skill。

## ⚠️ 关键约束

1. **只读** — 只调用 `email__list_emails_metadata` / `email__get_emails_content` / `email__download_attachment` / `email__list_available_accounts`。**严禁**调用 `email__send_email`、`email__delete_emails`。
2. **不伪造邮件内容** — 列表、正文、发件人、时间一律以工具实际返回为准，缺数据就说没有，绝不编造发件人/主题/正文。
3. **多账号必须先确认** — 见「账号选择」。不擅自替用户选邮箱。
4. **调用失败如实报告** — 工具报错原样贴出，不静默吞错、不假装查到了。
5. **附件保存路径在 workspace 内** — `save_path` 必须落在 workspace 相对目录下（见 Step 4），**绝不**用 `/tmp` 等绝对路径。

## 关于 MCP server 名称

本 skill 的邮件操作走 `email` MCP server，工具名格式为 `email__<tool>`（双下划线），如 `email__list_available_accounts`。参数照传，无需 agent_id。

## 账号选择

一个 agent 可能配了多个邮箱账号（如 talent-acquisition 有 nsdigital / antalpha / elevatesphere / ecohash / aurelion）。读哪个收件箱由下列规则决定，**优先级从上到下，命中即停**：

1. **用户已点名某个账号/公司** → 用该账号。把用户语义映射到 `account_name`：
   - `ns` / `nsdigital` → `nsdigital`
   - `antalpha` → `antalpha`
   - `elevatesphere` → `elevatesphere`
   - `ecohash` → `ecohash`
   - `aurelion` → `aurelion`

   匹配规则同发送类 skill：关键字必须作为**独立 token** 完整出现（被空白、标点、中文或边界包围），不区分大小写；不做模糊/前缀匹配（"ant"、"eco"、"ele" 都**不**匹配）。映射出的 `account_name` 必须属于 `list_available_accounts` 实时返回的集合，否则视为未命中。

2. **用户未点名** → 先跑 `list_available_accounts` 看有几个账号：
   - **恰好 1 个** → 直接用它，不询问。
   - **2 个及以上** → **停下来问用户**要看哪个邮箱，把可选账号列出来让用户选，例如：
     ```
     你有多个邮箱账号，想看哪个的收件箱？
     - NS (r.astro@nsdigital.io)
     - Antalpha (r.astro@antalpha.com)
     - Elevatesphere (r.astro@elevatesphere.com)
     - Ecohash (r.astro@ecohash.com)
     - Aurelion (r.astro@aurelion.com)
     ```
     （账号与邮箱以 `list_available_accounts` 返回的 `account_name` / `email_address` 为准，不要从本文档抄。）

> 拿账号清单：调用 `email__list_available_accounts`。
> 返回是数组，每项含 `account_name`、`email_address`、`full_name`。

## 执行流程

### Step 1：确定 account_name

按上面「账号选择」规则定下 `account_name`。多账号且用户没指定时，**先问用户再继续**，不要默认查第一个。

### Step 2：列出 / 搜索邮件

用 `list_emails_metadata` 拿邮件元数据（不含正文）。最常见就是"看最近收到的几封"：

```
email__list_emails_metadata(
  account_name="{account_name}",
  mailbox="INBOX",
  page_size=10,
  order="desc"
)
```

按需加过滤条件（都是可选参数）：

| 参数 | 说明 | 示例 |
|---|---|---|
| `from_address` | 按发件人邮箱过滤 | `from_address="hr@example.com"` |
| `to_address` | 按收件人过滤 | `to_address="r.astro@nsdigital.io"` |
| `subject` | 按主题过滤 | `subject="面试"` |
| `since` | 该时间之后（UTC） | `since="2026-05-01T00:00:00Z"` |
| `before` | 该时间之前（UTC） | `before="2026-05-20T00:00:00Z"` |
| `mailbox` | 邮箱文件夹，默认 INBOX | `mailbox="INBOX"` |
| `seen` | 已读/未读 | `seen=false`（只看未读） |
| `flagged` / `answered` | 星标 / 已回复 | `flagged=true` |
| `page` / `page_size` | 分页，默认 page=1 size=10 | `page=2 page_size=20` |
| `order` | 排序，`desc`=最新在前 | `order="desc"` |

> **搜索的局限**：过滤走 IMAP 服务端搜索，基于**元数据**（发件人/收件人/主题/时间/状态），**没有正文全文关键词搜索**。要按正文内容找，先用 `subject` / `from_address` / 时间缩小范围，再 Step 3 读正文自己判断。

**输出**：把返回的邮件按表格列给用户——发件人、主题、收到时间、`email_id`（后面读正文要用）。先不读正文，除非用户要求。

### Step 3：读取邮件全文（按需）

用户要看某封/某几封的正文时，用 `get_emails_content`，传 Step 2 拿到的 `email_id`：

```
email__get_emails_content(
  account_name="{account_name}",
  mailbox="INBOX",
  email_ids=["22"]
)
```

读多封一次传多个：`email_ids=["22","21","19"]`。

> ⚠️ **`email_ids` 必须是字符串数组**（元素是字符串）。传裸数字（`email_ids=22`）会被服务端拒绝并报：
> `Input should be a valid list [type=list_type]`。

返回每封含 `subject` / `sender` / `recipients` / `date` / `attachments`（附件名列表）/ `body`（正文）。把正文如实呈现给用户。

### Step 4：下载附件（按需）

用户要某封邮件的附件时，先从 Step 3 的 `attachments` 字段确认附件名，再下载：

```
email__download_attachment(
  account_name="{account_name}",
  email_id="22",
  attachment_name="resume.pdf",
  save_path="inbound/email-attachments/resume.pdf",
  mailbox="INBOX"
)
```

- `save_path` **必须是 workspace 相对路径**（推荐 `inbound/email-attachments/`）。若目录不存在，先 `bash_exec: mkdir -p inbound/email-attachments`。**绝不用 `/tmp` 等沙盒外绝对路径**——会被路径策略拒绝，`download_attachment` 会失败。
- 下载成功后告诉用户保存路径；若用户要拿到文件本身，用 `send_file(path="inbound/email-attachments/resume.pdf")` 把附件投递回当前对话。

### Step 5：错误处理

任何工具调用报错，**原样把错误贴给用户**，并按错误类型提示：

```
❌ 读取邮箱失败

错误：{工具返回的完整错误信息}
```

常见原因：
1. **`账号 X 未找到` / 账号不在返回里**：`email` MCP server 没配这个账号。让用户/运维确认 server 的邮箱账号配置是否有对应账号块。
2. **IMAP 连接/认证失败**（`LOGIN failed` / 超时）：收件邮箱（IMAP）凭据或 host/port 有问题，找运维核查（Gmail 需应用专用密码、`imap.gmail.com:993` SSL）。
3. **`Input should be a valid list`**：`email_ids` 没传成字符串数组，见 Step 3 修正。

## 前置条件

- `email` MCP server 已挂载并可用（工具名 `email__*`）。
- server 的邮箱账号已配置可用的 IMAP 收件配置，例如 Gmail：`imap.gmail.com:993`、SSL、应用专用密码。

## 冒烟测试

让 agent 执行下列动作验证读取链路通：

1. **列账号**：调用 `email__list_available_accounts`，确认返回数组每项含 `account_name`。
2. **列收件箱**（取最新 5 封元数据）：`email__list_emails_metadata(account_name="nsdigital", mailbox="INBOX", page_size=5, order="desc")`，应返回 `emails` 数组，每项有 `email_id` / `subject` / `sender` / `date`。
3. **读全文**（拿上一步任一 email_id）：`email__get_emails_content(account_name="nsdigital", mailbox="INBOX", email_ids=["<email_id>"])`，应返回含 `body` 的对象。
4. **端到端**：通过 Slack 让 agent 执行"看下最近收到的邮件"，确认它走 `email__list_emails_metadata` 并列出发件人/主题/时间，而不是声称自己没有邮箱能力。
