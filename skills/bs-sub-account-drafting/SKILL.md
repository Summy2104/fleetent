---
name: bs-sub-account-drafting
description: 子账户申请邮件起草。触发词：子账户、开账户、平台账户、sub account、子账户申请
status: active
metadata:
  author: BS Team
  version: 3.2.0
complexity: L2
---

# 子账户申请邮件起草

## 使用场景

- **NL 触发**：
  - "@star Trading 在 Binance 要开个子账户，用途现货"
  - "给 Trading 申请个子账户"
  - "帮我起草子账户申请邮件"
- **被其他 skill 调用**：M1 主流程节点 I（合同签完后触发）

## 前置条件

- `common-email-draft-gdrive` 有子账户申请模版（模版名称：`【通用】子账户申请模版-AI`）
- `armada` MCP server 已配置（NS 业务线查询，鉴权由 server env 注入，skill 不碰 token）
- `google-drive` MCP server 已配置（模版下载）

## 输入

**全部动态获取**：所有输入字段从邮件模版的「使用指南 - 变量替换说明」表格中解析，不在 skill 中硬编码。

模版中标记为「系统自动派生」的字段（如 `application_date`、`business_leader`、`business_group_email`）由 skill 自动获取，无需用户输入。

## 工作流程

### 主流程

```mermaid
flowchart TD
    A["用户触发 skill"] --> Z["Step 0: 鉴权预检（每轮 turn）"]
    Z --> B["Step 1: 下载模版并解析字段"]
    B --> C["Step 2: 收集用户输入"]
    C --> D["Step 3: NS 业务线模糊匹配 + 候选选择"]
    D --> G["Step 4: 派生字段二次确认 gate"]
    G --> E["Step 5: 生成邮件草稿"]
    E --> F["输出邮件草稿"]
    G -.->|用户回复"修改"| C
    Z -.->|sender_id 缺失| X["终止 + 固定话术"]
```

---

### Step 0：鉴权预检（每轮 turn 开头都要执行）

> 本段是简版。完整规则与 subagent 透传协议见 `common-ns-system-query/SKILL.md §Step 0`（父 skill，source-of-truth）。

1. 从 fleetent ToolContext（incoming 消息所携带的发送者身份）提取 `sender_id`
2. 校验 `sender_id` 匹配正则 `^U[A-Z0-9]{8,}$`
3. **任一校验失败** → 回复下列固定话术并终止：

   > ❌ 此 skill 仅限 Slack 渠道使用。当前上下文无法识别 Slack 用户身份，已阻止 NS 系统查询。

4. 通过 → 把 `sender_id` 作为本轮 Step 3 中每次 `ns-call.sh` 调用的**首个位置参数**传入（不写文件、不写 env，每次 `bash_exec` 显式传值）：

   ```bash
   bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
     get "/v1/biz_lines" \
     'query_params={"name":"...","status":1,"page_size":10}'
   ```

   `ns-call.sh` 校验通过后会打印一行 `ARMADA_CALL armada__armada_get path=... _meta={...}`，
   agent 据此发起 `armada__armada_get` 工具调用拿到 JSON。

5. **严禁**直接发起裸 `armada__armada_get` / `armada__armada_post` 工具调用——必须经 wrapper，
   绕过 wrapper 即绕过 `_meta.slackUserId` 注入，生产会被拒。

---

### Step 1：下载模版并解析字段

**1.1 获取模版**

优先从 workspace 本地索引获取模版信息（若 `common-email-template-sync` 已同步过）：
```bash
cat outbound/email-template-sync/template-index.json
```

若本地索引不存在，由 agent loop 发起 `google-drive__listFolder` 工具调用拉取目录列表（`folderId` = GDrive 邮件模版文件夹 ID）。

找到模版 `【通用】子账户申请模版-AI`，获取其 `fileId`。

**1.2 下载并转换模版**

1) 由 agent loop 发起 `google-drive__downloadFile` 工具调用，下载到 workspace（同时按 docx 导出）：

```
google-drive__downloadFile
  fileId: {fileId}
  localPath: outbound/email-draft-gdrive/sub-account.docx
  exportMimeType: application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

2) 用内置 `bash_exec` 跑 pandoc 转 markdown（容器预装 pandoc）：

```bash
mkdir -p outbound/email-draft-gdrive
pandoc "outbound/email-draft-gdrive/sub-account.docx" \
  -f docx -t markdown --wrap=none \
  -o "outbound/email-draft-gdrive/sub-account.md"
```

**1.3 解析输入字段**

读取转换后的 markdown 文件，定位「使用指南 - 变量替换说明」表格，解析出：
- 占位符名称（如 `{business_line}`）
- 说明
- 是否必填
- 示例值
- 来源（用户输入 / 系统派生）

将解析结果作为本次邮件起草的输入字段定义。

---

### Step 2：收集用户输入

**2.1 询问语言偏好**

```
请选择邮件语言版本：
1. 中文
2. 英文
3. 双语
```

**2.2 逐项收集模版字段**

根据 Step 1.3 解析出的字段列表，对「用户输入」类型的字段逐项询问：

```
请提供以下信息（按 Enter 跳过可选项）：

业务线名称（{business_line}，必填，示例：Defi / Trading / 量化）：
项目号（{project_id}，必填，示例：Defi00329）：
子账户创建平台（{platform_name}，必填，示例：Binance / OKX / Gate）：
...
```

**注意**：
- 必填字段不可跳过
- 可选字段允许留空
- 「系统派生」类型的字段（如 `application_date`、`business_leader`、`business_group_email`）不询问

---

### Step 3：NS 业务线模糊匹配 + 候选选择

根据模版中标记为「系统派生」的字段（`application_date` / `business_leader` / `business_group_email`）执行查询。所有 NS 调用必须经父 skill `common-ns-system-query` 的 wrapper（见 Step 0 第 4 条）。

**3.1 application_date**（若模版中存在）

```
application_date = 当前日期，格式 YYYY-MM-DD
```

**3.2 业务线模糊匹配**（若模版中存在 `business_leader` 或 `business_group_email`）

Reference 加载（每轮一次）：

```bash
cat $SKILLS_DIR/common-ns-masterdata/references/business-config-biz-activity.md
```

**输入校验**（在调 NS 之前）：

- Step 2 收集的 `business_line` 字符串去空白后**长度 < 2** → 回复「业务线名称至少需要 2 个字符，请补全」，**不触发查询**，停留在 Step 2
- 长度 ≥ 2 → 进入模糊查询

**调用**：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines" \
  'query_params={"name":"<去空白后的 business_line>","status":1,"page_size":10}'
```

`bash_exec` 跑上面命令拿到 `ARMADA_CALL armada__armada_get path=/v1/biz_lines ...` 行后，
agent 据此发起 `armada__armada_get` 工具调用拿 JSON，再按下方 `match_count` 规则处理。

- `name` 参数 NS 端原生支持模糊匹配
- `page_size=10` 等于 R03 的 `max_results` 默认值
- `status:1` 限定启用业务线
- `"$UID"` 是占位符，agent exec 时替换为 Step 0 提取的 `sender_id`

**响应处理**（按 `match_count`，即 `list.length`）:

| `match_count` | 行为 |
|---|---|
| 0 | 回复零候选标准文案 |
| 1 | **不自动采用**。展示候选表格（仅 1 行）+ 要求用户回复「1」或「y」 |
| 2 ~ 10 | 展示候选表格 |
| `page_info.total > 10` | 回复超上限文案，仍展示前 10 条 |

**候选表格模板**（命中 1 ~ 10 条统一）：

```
🔎 找到 {match_count} 条业务线候选：

| # | 业务线名称 | 简称 | 候选 leader | 候选 group |
|---|----------|------|------------|----------|
| 1 | NS-Trading | Trading | foo@nsdigital.io | trading@nsdigital.io |
| 2 | NS-Trading-Asia | Trading-Asia | 多个负责人 | bar@nsdigital.io |
| 3 | NS-Trading-Quant | Trading-Quant | baz@nsdigital.io | 无邮件组 |

请回复序号 1–{match_count} 选择，或回复「0」回 Step 2 重输业务线名称。
（match_count=1 时，回复「1」或「y」均视为确认。）
```

字段映射（来自 `/v1/biz_lines` 响应 `list[]`）：

| 列 | 源字段 | 取值规则 |
|----|--------|---------|
| 业务线名称 | `name` | 原样 |
| 简称 | `abbreviation` | 空时显示 `—` |
| 候选 leader | `owners[]` | `length==0` → `空`；`length==1` → `owners[0].email`；`length>1` → `多个负责人` |
| 候选 group | `email_group[]` | `length==0` → `空`；`length==1` → `email_group[0]`；`length>1` → `多个邮件组` |

**零候选文案**：

```
🔎 没找到匹配「{business_line}」的业务线（NS-Masterdata 仅返回启用状态业务线）。
- 请检查拼写或换关键词（如简称、英文名、所属公司主体）
- 也可回复「manual」改为手填 leader 邮箱与邮件组
```

**超上限文案**（`page_info.total > 10`）：

```
🔎 命中 {total} 条，超出展示上限（10）。请补充关键词（如完整名称 / 部门 / 公司主体），或回复序号 1–10 选当前页。
```

**3.3 owner / group 多值短问**（仅当用户在 3.2 选定的业务线对应字段为多值时）

`owners.length > 1` 时：

```
该业务线 {name} 有 {N} 位负责人，请选 leader 邮箱：

| # | 邮箱 | 昵称 |
|---|------|------|
| 1 | foo@nsdigital.io | Foo |
| 2 | bar@nsdigital.io | Bar |

请回复序号 1–{N}。
```

`email_group.length > 1` 时：

```
该业务线 {name} 有 {N} 个邮件组，请选 group：

1. trading@nsdigital.io
2. trading-asia@nsdigital.io

请回复序号 1–{N}。
```

两个字段都多值时，按 owner → group 顺序连续短问。

**3.4 owner / group 缺失手填**

若选定业务线 `owners.length == 0` 或 `email_group.length == 0`：

```
业务线「{name}」未配置 {leader 邮箱 | 邮件组}，请直接输入 {leader 邮箱 | 邮件组邮箱地址}：
```

用户回复用 `^[^\s@]+@[^\s@]+\.[^\s@]+$` 校验，不通过重新追问。手填后仍需经 Step 4 二次确认。

---

### Step 4：派生字段二次确认 gate

Step 3 完成后、生成草稿前，向用户发一条独立消息汇总即将填入草稿的派生字段，要求显式确认。**不论字段是否唯一命中、不论是否手填，都必须经过本步**（与 R04 §8「单候选也要确认」原则对齐）。

**消息模板**：

```
📋 即将生成 {language_label} 邮件草稿，请确认派生字段：

- 申请日期（application_date）：{YYYY-MM-DD}
- 业务线：{name}（biz_line_id={id}）
- 业务线 leader（business_leader）：{email}{来源标记}
- 业务线邮件组（business_group_email）：{email}{来源标记}

回复「确认」继续生成草稿，或回复「修改」重新选业务线。
```

`{language_label}` 取值：`中文` / `英文` / `双语`，沿用 Step 2.1 用户选择。

`{来源标记}`：
- 来自 NS 单候选（owners/email_group 唯一） → 不加标记
- 来自 NS 多候选用户挑选 → ` (NS 多选)`
- 来自手填（Step 3.4） → ` (手填)`

**用户回复处理**：

| 用户输入（trim + lower-case） | 行为 |
|------|------|
| `确认` / `ok` / `go` / `y` | 进入 Step 5 |
| `修改` / `重选` / `n` | 回 Step 2 重输 `business_line`（清掉旧 `business_line` 与所有派生字段：leader/group/biz_line_id），其它已收集字段（language、模板其它必填项）保留 |
| 其它 | 回复「请回复『确认』或『修改』」，不推进 |

---

### Step 5：生成邮件草稿

**5.1 选择邮件版本**

根据用户选择的 `language`：
- 中文：使用模版中「中文版」部分
- 英文：使用模版中「English Version」部分
- 双语：两个版本都输出

**5.2 替换占位符**

将所有 `{xxx}` 占位符替换为收集到的值。

**5.3 输出格式**

直接输出纯文本，不使用 markdown 代码块。

---

## 异常处理

| 异常情况 | 处理方式 |
|----------|----------|
| 模版不存在 | 提示模版缺失，联系管理员补充 |
| 模版解析失败 | 提示模版格式异常，检查「使用指南」表格是否完整 |
| Step 0 sender_id 缺失/格式不合法 | 回复 Step 0 固定话术并终止，不发起任何 NS 调用 |
| 业务线输入字符 < 2 | 回复「业务线名称至少需要 2 个字符，请补全」，停留在 Step 2 |
| 业务线查询零候选 | 回复 Step 3.2 零候选文案（含拼写检查 + 换关键词 + manual 分支） |
| 业务线候选 > 10 | 回复 Step 3.2 超上限文案 |
| 用户在二次确认 gate 回复「修改」 | 回 Step 2 重输 `business_line`，清掉派生字段，其它字段保留 |
| 业务线 `owners` 数组为空 | 提示用户手填 leader 邮箱（email 正则校验），手填后仍经 Step 4 二次确认 |
| 业务线 `email_group` 数组为空 | 提示用户手填邮件组邮箱（email 正则校验），手填后仍经 Step 4 二次确认 |
| MCP 连接失败 | 提示检查 `armada` / `google-drive` MCP server 状态 |
| NS wrapper 返回非 0 退出码 | `ERR_AUTH_INVALID`（uid 格式不合法）按 Step 0 固定话术；其它 exit code 原样透传 |

## 依赖

- `common-email-draft-gdrive` — 邮件模版下载与转换
- GDrive 邮件模版 `【通用】子账户申请模版-AI`
