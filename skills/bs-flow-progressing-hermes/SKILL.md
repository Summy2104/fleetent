---
name: bs-flow-progressing-hermes
description: >
  用户主动查询审批流程状态，汇总展示"我发起的"和"待我审批的"流程，
  支持交互式/自然语言/批量三种方式发送 Slack 催办私信，
  以及被催办人在催办消息下 thread reply 数字（1=收到 / 2=已完成）或"收到"关键词后自动通知催办人形成闭环。
  触发词：审批进度、我的流程、查流程、流程状态、催审批、催一下、审批到哪了、收到、已收到
status: active
metadata:
  author: RD Team
  version: 2.11.0
  platform: fleetent
complexity: L3
---

# 流程进度查询与催办

## 使用场景

- 查询自己相关的审批流程状态："@star 查一下我的审批进度"、"@star 待我审批的流程"
- 催办审批人："@star 催一下王总审批 20260421015"、"@star 催办超时的审批"
- **收到回应**：被催办人在催办消息下 **thread reply** 数字（`1`=收到 / `2`=已完成）或关键词 `收到`，agent 自动通知原催办人（详见 Step 5）

## 前置条件

- 用户 Slack 账号已与 NS 系统用户关联（通过邮箱匹配）
- NS `/v1/bpmn/dashboard/all`、`/v1/management/approver/list`、`/v1/users` 可访问

## 输入

| 字段 | 类型 | 必填 | 来源 |
|------|------|------|------|
| slack_user_id | string | yes | Slack 上下文 |
| action | enum | no | 用户指令解析：`query` / `remind` / `remind_all` |
| target_approver | string | no | 催办目标姓名或 Slack mention |
| process_no | string | no | 11 位流程编号 |

## 输出规范（所有 Step 通用，必须严格遵守）

### ❌ 严禁向用户暴露的内容

| 类型 | 反例（禁止） | 说明 |
|------|------------|------|
| Skill 加载过程 | "我先读取一下 bs-flow-progressing skill" / "按照 bs-flow-progressing skill 的流程" | 内部行为，用户无感 |
| Step 编号引用 | "根据 SKILL.md Step 5.5-F 的规则" / "进入 Step 4.2" / "走 Step 5.5 异常处理" | 实现细节，用户不关心 |
| 思考 / 计划过程 | "让我先确认..." / "现在我需要..." / "我应该..." / "完美！" / "好的，按照..." | 思维链不应回显 |
| 内部技术术语 | "endpoint" / "wrapper 路径" / "tasks 端点" / "API 接口" / `current_assignee` / `mongo_id` | 用业务语言：邮箱、流程编号、节点、审批人 |
| 原始 Slack ID 文本 | `U0555FN1REX`（裸字符串） | 必须用 `<@U0555FN1REX>` mention 格式 |
| 已完成的查询步骤 | "1. 先查 X / 2. 展示 Y / 3. 等待 Z" 这种步骤罗列 | 直接给结果，不报告流程 |
| 任何 SKILL.md 字段名 | `slack_bind` / `ns_username` / `n_remaining` / `overdue_hours` | 中文化或不提 |

### ✅ 正确的输出风格

- **结果优先**：直接给用户要的信息，不解释你做了什么、查了哪里
- **业务语言**：邮箱、流程编号、节点、等待时长，不要技术术语
- **Slack mention**：所有 Slack ID 都用 `<@Uxxx>`，让 Slack 渲染为用户名链接
- **简洁错误**：报错时只说现象 + 下一步建议，不暴露 stack trace / 字段名
- **直接行动**：能用工具调用解决的（如发消息），就直接调，不要先说"我现在准备调用..."

### 反例 → 正例

| ❌ 反例 | ✅ 正例 |
|--------|--------|
| "我先读取一下 bs-flow-progressing skill，看看催办的正确流程" | （什么都不说，直接干活） |
| "完美！我获取到了 zhangliang 的 Slack ID: U0555FN1REX" | （什么都不说，直接进入下一步） |
| "催办人和被催办人是同一个人！" / "您要催办的是您自己" | （不识别也不提示，按普通催办流程走） |
| "现在我需要将这个消息发送给用户" | （直接调 send_im_message，无需预告） |
| "1. 先查邮箱<br>2. 展示确认<br>3. 等待确认" | （直接展示确认卡片，让用户点按钮） |
| "目标审批人：zhangliang (U0555FN1REX)" | "目标审批人：<@U0555FN1REX>" |

### 唯一例外

工具调用**失败**时，可以告知用户失败原因（如 "NS 系统暂时不可用"）—— 但仍要避免内部字段名 / endpoint 路径。

## 工作流程

> **armada 调用范式（两步交互，全 Step 通用）**：本 skill 所有 NS 查询都经 `scripts/ns-call.sh`（唯一合法入口）。
> 它不直接返回 JSON——而是校验 uid + 构造参数后打印一行 `ARMADA_CALL armada__armada_<method> path=... ... _meta=...`。流程：
> ① 用 `bash_exec` 跑 ns-call.sh 拿到 `ARMADA_CALL` 行；② agent 据此行发起 `armada__armada_get`（或 `armada__armada_post`）MCP
> 工具调用（参数 = path + 后续 kv + `_meta`）拿 JSON；③ 如需 jq / 合并 / 裁剪，再用 `run_code` 处理。
> 切勿假设沙箱里直接拿到 armada JSON。`sender_id` 透传：ns-call.sh 首参 `$UID` 即 ToolContext 里发起人的 Slack user ID。

### Step 0/1 NS 用户身份验证

从 ToolContext 取 `sender_id`（即发起人 Slack user ID），查询 NS 用户：

```bash
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/users" \
  'query_params={"slack_id": "<sender_id>", "page_size": 5}'
```
拿到 `ARMADA_CALL` 行后发起 `armada__armada_get` 工具调用取 JSON。

- 按 `slack_id` 精确匹配筛选，取第一条匹配记录
- `list.length == 0` → 提示"NS 系统中未找到该用户"，终止
- 取 `id`=`ns_user_id`、`nickname`=`ns_username`

### Step 2 并行查询流程

**查询"我发起的"**：
```bash
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/dashboard/all" \
  'query_params={"starter": "<ns_username>", "process_state": "running", "page": 1, "page_size": 50}'
```
拿到 `ARMADA_CALL` 行后发起 `armada__armada_get` 工具调用取 JSON。

**查询"待我审批的"**（需先取 approver_id）：

```bash
# 1. 用 ns_username 取 approver_id（user_name 精确匹配）
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/management/approver/list" \
  'query_params={"user_name": "<ns_username>", "page_size": 5}'
```

发起 `armada__armada_get` 取响应，取 `list[].id`（按 `user_name` 精确匹配筛选）作为 `approver_id`。

```bash
# 2. 用 approver_id 查待审批流程
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/dashboard/all" \
  'query_params={"approver_id": "<approver_id>", "process_state": "running", "page": 1, "page_size": 50}'
```
同样发起 `armada__armada_get` 取 JSON。两个列表的合并/去重用 `run_code` 处理。

按 `mongo_id` 合并去重（同一流程可能同时出现在两个列表）。计算 `waiting_hours = (now - created_at) / 3600`，超过 48h 标记超时。

### Step 3 汇总展示

以表格形式分两组展示：

**我发起的**（列：编号、标题、当前节点、审批人、等待时长、超时标记）
**待我审批的**（列：编号、标题、发起人、等待时长）

无流程时展示"您当前没有进行中的流程 🎉"。

操作提示：
- 回复流程编号查看详情
- 回复"催 @姓名"发送催办私信
- 回复"催办超时"一键催办所有超时审批人

### Step 4 催办功能（可选）

**上下文继承规则（优先级最高）**：若当前对话已有明确 `process_no`（如用户刚查完某条流程详情），催办直接使用该流程，不重新搜索，不扩展到其他流程。

#### 触发方式

| 用户输入 | 处理 |
|----------|------|
| 上下文已有流程号 + 指定催办对象 | 直接进入 Step 4.1 |
| 指定姓名 + 流程号 | 直接进入 Step 4.1 |
| 指定姓名、无流程号 | 列出该审批人相关的待审批流程，用户选择后进入 Step 4.1 |
| "催一下"/"催办"（无目标） | 列出所有待审批人供选择，用户选择后进入 Step 4.1 |
| "催办超时"/"一键催办" | 筛选 `waiting_hours > 48` 的审批人，进入 Step 4.1 |

> **催办人 = 被催办人时**（催办人本身是审批人之一），完全按普通流程处理：正常发二次确认、正常发催办 DM、正常发 5.3 + 5.4 两条通知。**不要识别 / 不要提示 / 不要做任何特殊处理**。用户看到的体验和催办他人完全一致。

#### Step 4.1 二次确认（必须，不可跳过）

> **模糊编号处理**：用户提供的编号在 NS 系统中不存在时，尝试模糊匹配（如用户写 `20260526032` 但实际是 `20260526033`，可以用 `process_no=2026052603` 前缀查询后列出候选供用户选择）。示例：`bash_exec` 跑 `ns-call.sh "$UID" get "/v1/bpmn/dashboard/all" 'query_params={"process_no": "<前缀>", "page": 1, "page_size": 10}'`，再据 `ARMADA_CALL` 行发起 `armada__armada_get`。

**所有催办操作在发送私信前，必须先展示目标用户信息并等待用户确认。** 催办人**点确认按钮或回复文本**均可（见下方确认按钮卡片）。

**4.1.1 查找目标审批人 Slack ID**

**重要**：`current_assignee` 字段可能包含多个逗号分隔的用户名（如 `"xin001,Lilac,xin.cheng"`）。必须**只查用户指定的目标姓名**，不得遍历 `current_assignee` 中的其他人。

```bash
# 1. 用用户名取邮箱（只查用户指定的目标，如 "xin.cheng"）
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/management/approver/list" \
  'query_params={"user_name": "<approver_username>", "page_size": 5}'

# 2. 用邮箱取 slack_id（必须执行此步，禁止从记忆/其他来源取 Slack ID）
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v1/users" \
  'query_params={"email": "<approver_email>", "page_size": 5}'
```
（每条都先 `bash_exec` 拿 `ARMADA_CALL` 行，再发起 `armada__armada_get` 取 JSON）

> ⚠️ **Slack ID 必须通过 NS 用户表查询获取**：禁止从本地记忆、历史会话、或其他来源复用 Slack ID。NS 用户表中的 `slack_id` 是唯一可信来源，直接决定催办消息发送对象。使用错误 Slack ID 会导致催办发送到错误的人。

**确认消息的发送位置（强约束）**：

二次确认消息**必须直接回复在用户调用催办的当前会话**（channel / thread / DM 任一，用户在哪发起就在哪回），**禁止主动切到 DM**。也就是：

- ❌ 不要 `to: "slack:<sender_slack_id>"`（这会把确认消息塞进 DM）
- ❌ 不要说"已发送确认消息到您的私信，请到 DM 中确认"等转跳话术
- ✅ 直接在当前会话中以 agent 默认 reply 的方式输出确认信息（不指定 `to` 字段）

展示确认信息（包含：用户名、邮箱、流程编号、标题、等待时长；用 `<@U...>` mention 格式代替裸 Slack ID）。

**确认提示（必须等待用户确认）**：在确认信息正文之后，用内置 `clarify` 工具向用户提出确认问题，
options 为「确认催办 / 取消」两项；用户也可直接回复文本（"确认"/"取消"等）。

> NOTE (fleetent): 原 hermes 版在确认正文后输出一个 ```buttons``` 围栏（由网关渲染成 Slack 确认/取消按钮）。
> fleetent 下用内置 `clarify` 工具表达这组二选一确认（或直接以文本枚举让用户回复），语义等价；非 Slack 渠道用户照常文本回复即可。
> 不要拼 Slack Block Kit、不要找"卡片脚本"，直接调 `clarify` 或输出文本枚举。

等待用户确认（点 `clarify` 选项 或 回复文本）：
- "确认"/"是"/"发送"（或选「确认催办」）→ 进入 Step 4.2
- "取消"/"否"/"算了"（或选「取消」）→ 终止，提示"已取消催办"
- `slack_bind != 1` 或 `slack_id` 为空 → 仅将**该人**从发送列表排除，标注"⚠️ 该用户未绑定 Slack，无法发送私信"；**不影响其他已绑定用户，不终止整个催办流程**
- 若用户指定了催办目标（如"催一下 xin.cheng"），**只查 xin.cheng 的绑定状态**，不查 `current_assignee` 中的其他人

#### Step 4.2 发送催办私信

**4.2.1 获取审批上下文（必须执行，不得跳过）**

```bash
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/tasks" \
  'path_params={"mongo_id": "<mongo_id>"}'
```
（拿 `ARMADA_CALL` 行后发起 `armada__armada_get` 取 JSON）

字段提取规则详见 `references/approval-history.md`。

`waiting_time` 计算规则：
- 取已完成节点中最后一个的 `operate_time` 作为当前节点开始等待的时间
- `waiting_hours = (now - last_completed_operate_time) / 3600`
- `/tasks` 接口失败时降级用 `(now - created_at) / 3600`
- 格式化为中文时长，精确到分钟，如"3小时12分钟"、"45分钟"

`overdue_hours = waiting_hours - 48`，`waiting_hours ≤ 48` 时为 0。

**4.2.2 发送私信**

```bash
# Step 1：生成纯文本
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/send-reminder.sh "$UID" \
  "mongo_id=<mongo_id>" \
  "process_no=<process_no>" \
  "email_subject=<email_subject>" \
  "waiting_time=<waiting_time>" \
  "task_name=<task_name>" \
  "starter_name=<starter_name>" \
  "sender_slack_id=<sender_slack_id>" \
  "overdue_hours=<overdue_hours>" \
  "last_actor=<last_actor>" \
  "last_action=<last_action>" \
  "last_comment=<last_comment_excerpt>" \
  "remaining_chain=<remaining_chain_brief>" \
  "n_remaining=<n_remaining>"
```

```
# Step 2：用内置 send_im_message 把 send-reminder.sh 的 stdout 原文发给被催办人私信
send_im_message:
  target: slack:<target_slack_id>
  text: <send-reminder.sh stdout 原文>
```

被催办人的回应闭环走 **thread reply 数字 / 关键词**（见 Step 5）——这是 fleetent 下的主路径，无需额外按钮即可形成闭环。

> NOTE (fleetent): 原 hermes 版在催办 DM 上挂了一个「✅ 已知悉」回调按钮（点击由网关确定性 DM 催办人、不经 LLM）。
> fleetent 内置 `send_im_message` 当前不支持结构化回调按钮（notify callback），故移除该按钮分支；
> 闭环统一走 Step 5 的 thread reply（回复 `1`/`2`/`收到`）。接入支持回调按钮的能力后可恢复「已知悉」一键回执。

参数说明：
- `sender_slack_id`：催办人 Slack ID（即 Step 0/1 的 `sender_id`）。消息底部会显示 "🙋 催办人：<@xxx>"
- `overdue_hours`：`waiting_hours - 48`，`waiting_hours ≤ 48` 时传 `0`
- `last_actor` / `last_action` / `last_comment`：4.2.1 接口成功且有已完成节点时填入，否则传空字符串 `""`
- `n_remaining`：未完成节点数；接口失败时传 `-1`（脚本跳过后续审批行）

催办后记录目标和时间，1小时内避免重复催办同一人。

### Step 5 收到回应（数字 / 关键词 thread reply 触发）

被催办人在 R. Star 发出的催办消息下用 **thread reply** 回复**数字 1 / 2** 或**关键词 "收到"** 即可触发，自动通知催办人。

> ⚠️ **强制执行约束（必读）**：识别到合法触发后**必须**通过 `send_im_message` **实际调用**发出 5.3 + 5.4 两条通知，**禁止**用大模型自由文本（如"好的，已收到"）代替任何一次工具调用。允许工具调用**完成后**在 thread 里加一句友好结尾（如"还需要其他帮助吗？"），但**不能用结尾代替工具调用**。详见 5.6 自检清单。

#### 5.1 触发识别（必须 thread reply）

**前置条件**（同时满足）：
1. 消息含 `thread_ts`（即用户的回复是 thread reply，不是 DM 主流的独立消息）
2. Thread parent 是 R. Star 发出的催办消息（消息文本以 `🔔 审批提醒` 开头）

**识别规则**（任一命中即视为收到回应意图）：

| 类型 | 匹配模式 | 对应动作 | 说明 |
|------|---------|---------|------|
| 数字 1 | 消息 trim 后等于 `"1"` 或 `"1️⃣"` | **收到** | 已收到，正在处理 |
| 数字 2 | 消息 trim 后等于 `"2"` 或 `"2️⃣"` | **已完成** | 已在 NS 系统中操作完毕 |
| 关键词 | 消息含 `"收到"` / `"已收到"` / `"收到 <11 位数字>"` | **收到** | 与数字 1 等价 |

**不识别的情况**（避免误触发）：
- 无 `thread_ts`（DM 主流孤立发"1"）→ 不进入 Step 5
- Thread parent 不是 R. Star 催办消息 → 不进入 Step 5
- 消息含数字但不是单纯的"1"/"2"（如 `"1234"`、`"1 处理完了"`）→ 不识别
- 单字符数字 > 2（如 `"3"`、`"9"`）→ 5.5 异常路径 A（提示"请回复 1 或 2"）

#### 5.2 解析流程号 + 催办人

Thread parent（催办消息）必含完整上下文：
- 正则 `（(\d{11})）` 提取 `process_no`
- 正则 `🙋 催办人：<@(U[A-Z0-9]+)>` 提取 `sender_slack_id`
- 正则 `📄 (.+?)（` 提取 `email_subject`

`recipient_slack_id` 即触发本 Step 5 的消息发送方（被催办人本人，从 Slack 上下文 `sender_id` 取）。

任一字段拿不到 → 5.5 异常路径 B（"无法识别原催办消息"）。

#### 5.3 通知催办人（**强制调 send_im_message**）

按用户选择的动作（收到 / 已完成）生成不同消息内容：

**动作 = 收到**（数字 `1` 或关键词命中）：

```
send_im_message:
  target: slack:<sender_slack_id>
  text: ✅ <@<recipient_slack_id>> 已收到你催办的流程 *<process_no>*
```

**动作 = 已完成**（数字 `2`）：

```
send_im_message:
  target: slack:<sender_slack_id>
  text: 🎉 <@<recipient_slack_id>> 已完成流程 *<process_no>*（<email_subject>） — 已在 NS 系统中操作，请到 NS 确认状态
```

**执行约束**：调用工具后必须确认返回成功；若失败，跳 5.5 异常处理（显式告知失败原因），**禁止假装发送成功**。工具调用尚未发出或返回错误时，严禁用任何文本（如"已提醒"、"通知已发出"）代替实际工具调用——这是 5.5-E 明令禁止的行为。

#### 5.4 回复被催办人确认（**强制再调一次 send_im_message**）

5.3 完成后，**必须再调用一次**（与 5.3 完全独立的第二次）`send_im_message` 回复被催办人，让其确认通知已发出。

**动作 = 收到**：

```
send_im_message:
  target: slack:<recipient_slack_id>
  text: ✅ 已收到 *<process_no>*，已通知 <@<sender_slack_id>>
```

**动作 = 已完成**：

```
send_im_message:
  target: slack:<recipient_slack_id>
  text: 🎉 已记录完成 *<process_no>*，已通知 <@<sender_slack_id>>
```

> 注意：5.3 是 DM 给**催办人**的（被催办人看不到），5.4 是给**被催办人**的确认。两条不能合并、不能省略，必须分别两次 `send_im_message` 工具调用。

#### 5.5 异常处理

| 场景 | 处理 |
|------|------|
| A. 数字 > 2（如 `"3"`、`"9"`） | thread reply 提示 "请回复 `1`（收到）或 `2`（已完成），其它数字无效" |
| B. 无法从 thread parent 解析 `process_no` 或 `sender_slack_id` | 回复"无法识别原催办消息，请直接告诉我流程号：`收到 <11 位编号>`" |
| C. Thread parent 不是 R. Star 催办消息 | 不进入 Step 5，按其它路径处理 |
| D. 无 thread_ts（DM 主流孤立"1"或"收到"） | 不进入 Step 5，按其它路径处理（agent 可询问"想回应哪条催办？请在催办消息下 thread reply"）|
| E. `send_im_message` 调用失败 | 显式告知失败原因（如 "通知催办人时 API 返回错误：xxx"），**禁止吞错装成功**。工具调用未发出或报错时，**严禁**用文本"已提醒""已通知"等代替实际调用结果 |
| F. 用户在 thread 里附加内容（如 `"1 处理完了"`） | 不属于单字符数字，不识别（5.1 不识别）。如包含关键词"收到"则按收到回应处理，附加内容作为 comment 拼到 5.3 消息末尾 |
| G. 重复回应同一流程 | 仍通知，但 5.3 消息加备注 "（今天第 N 次回应）" |

> **`sender_slack_id == recipient_slack_id`（催办人 = 被催办人）按普通流程处理**：5.3 + 5.4 都正常发，用户会收到两条消息（一条以催办人身份、一条以被催办人身份）。这是预期行为，**不做去重 / 不做合并 / 不提示**。

#### 5.6 完成前自检清单（agent 必须逐条 ✓）

输出最终响应前，agent 必须在思维链中确认以下**全部 ✓**：

- [ ] 我已通过 `send_im_message` **实际调用**（不是想象/计划）向催办人 `<sender_slack_id>` 发送了 5.3 通知
- [ ] 我已通过 `send_im_message` **实际调用**向被催办人 `<recipient_slack_id>` 发送了 5.4 确认
- [ ] 两次工具调用都返回成功（失败则走 5.5 异常）
- [ ] 我没有用 "好的，已收到" 之类自由文本**代替**任何一次工具调用
- [ ] 即使 `sender_slack_id == recipient_slack_id`（催办人自己），两条消息都正常发，**不跳过任何一条**

> 工具调用**完成后**可以在 thread 里追加一句友好结尾（如 "✓ 已处理完毕。还需要其它帮助吗？"），但**不能用结尾代替工具调用**。

任一条不满足 → 本轮未完成。**禁止表面回复"已收到"实际 send_im_message 一次都没调**。

## 异常处理

| 场景 | 处理 |
|------|------|
| 邮箱获取失败 | 提示确认 Slack 账号已设置邮箱，终止 |
| NS 用户不存在 | 提示"NS 系统中未找到该用户"，终止 |
| NS API 超时 | 重试 1 次，仍失败提示"NS 系统暂时不可用，请稍后重试" |
| 无进行中流程 | 展示"您当前没有进行中的流程 🎉" |
| 催办对象未绑定 Slack | 提示"该用户未绑定 Slack，无法发送私信，请直接联系 {姓名}" |
| 1小时内重复催办 | 提示"您已在 1 小时内催办过 {姓名}，请稍后再试" |
| 用户取消确认 | 提示"已取消催办"，终止 |
| 回应时无法解析原催办消息 | Step 5.5-B：回复"无法识别原催办消息，请直接告诉我流程号：`收到 <11 位编号>`" |
| 回应数字 > 2（如回了"3"）| Step 5.5-A：提示"请回复 `1`（收到）或 `2`（已完成）" |
| 被催办人未 thread reply 而是 DM 主流发"1" | Step 5.5-D：提示"想回应哪条催办？请在催办消息下 thread reply" |
| send_im_message 发送回应通知失败 | Step 5.5-E：显式告知失败原因，禁止吞错 |

## 边界

- 不自动轮询，仅用户主动触发
- 不做审批决策
- 仅查 `running` 状态流程
- 仅支持 Slack 私信催办

