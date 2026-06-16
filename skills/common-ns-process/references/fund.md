# 资金管理 (Fund) 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #1**：若入参是流程编号（11 位数字），先按父 skill `references/common-query-chains.md#链-1` 先转 instance_id 再查。

用户通常提供流程编号（如 `20260302011`），需先转换为 mongo_id 再查资金数据。

**展示规则**：资金计划、资金路径、资金信息三个接口，若返回 `list` 为空数组，则静默跳过，不向用户输出"未找到"或"列表为空"等提示；有数据才展示。

**执行规则（硬性）**：本文档的第 1-4 步是**一次"流程详情"查询的标准流水线，必须全部执行**。第 4 步是强制探测（三接口必调），只有 `list` 全空时才跳过展示，但接口调用不能省。第 5 步"审批历史"按触发条件决定是否加载，但无论如何不得影响前四步的执行。**禁止以"用户只问流程详情/为了省 token/判断资金数据不相关"为由跳过第 4 步**。

**占位符约定（反幻觉）**：文档示例里的 `<PROCESS_NUMBER>` / `<INSTANCE_ID>` / `task-456` / `active-task-id` **都是占位符**，不是真实值。每次查询必须：
1. 用用户给的**真实**流程号调第一步，拿到**真实** mongo_id；
2. 把真实 mongo_id 传给后续步骤，**严禁**把占位符当值发出去，也**严禁**复用上一次会话缓存的 id；
3. 自检：后续任何接口请求里的 mongo_id 长度应为 24 位十六进制（如 `69a64999b22eda04423ef08c`），不是 `<INSTANCE_ID>` 或任何旧值。

---

## 第一步：流程编号 → mongo_id

`GET /v2/bpmn/process_instance/number/{instance_number}`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| instance_number | string | 流程编号（如 `<PROCESS_NUMBER>`） |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id)，后续查询所需 |

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/number/{instance_number}" \

  'path_params={"instance_number": "20260302011"}'
# 返回: {"mongo_id": "69a531074474d7dd34c67bd8"}
```

---

## 第二步：查询流程实例详情

`GET /v2/bpmn/process_instance/{mongo_id}`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | 流程状态：running=审批中，completed=已完成，canceled=已撤销 |
| active_camunda_task_id | string | 当前活动任务 ID，用于查询当前审批任务详情 |
| is_fund_changing | boolean | 是否正在进行资金变更 |
| basic_info.process_number | string | 流程编号 |
| basic_info.process_definition.name | string | 流程定义名称 |
| basic_info.process_definition_type.name | string | 流程类别名称 |
| basic_info.starter_name | string | 发起人 |
| basic_info.created_at | string | 创建时间 |
| basic_info.custom_email_title | string | 流程标题 |
| basic_info.biz_lines | array | 业务线列表（含 id 和 name） |
| basic_info.company | array | 主体列表（含 id、name、relation_ids、relation_names） |
| basic_info.customer | array | 客户列表（含 id、name） |
| basic_info.project_numbers | array | 项目列表（含 id、name） |
| basic_info.memo | string | 备注 |
| basic_info.instruction | string | 说明（HTML 格式） |
| basic_info.attachments | array | 附件列表（含 id、title、link） |
| basic_info.related_emails | array | 关联邮件标题列表（字符串数组，每项为一封关联邮件的完整标题） |
| basic_info.email_tos | array | 邮件收件人列表（邮箱字符串数组，通常较长） |
| basic_info.email_ccs | array | 邮件抄送人列表（邮箱字符串数组） |
| basic_info.parent_process_number | string | 父流程编号 |
| basic_info.version | string | 版本 |

**展示规范**

流程详情以表格展示以下字段：

| 展示字段 | 数据来源 |
|---------|---------|
| 流程编号 | basic_info.process_number |
| 流程定义名称 | basic_info.process_definition.name |
| 流程标题 | basic_info.custom_email_title |
| 发起人 | basic_info.starter_name |
| 创建时间 | basic_info.created_at，转 UTC+8 格式 `YYYY-MM-DD HH:MM:SS`；**输出时时间值必须用反引号包裹**（如 `` `2026-04-09 16:21:15` ``），否则 Slack 会把 `:21:` 这种片段误识别为 emoji 短代码 |
| 流程状态 | status |
| 业务线 | basic_info.biz_lines[].name，多个用顿号连接 |
| 主体 | basic_info.company[].name，非空时展示 |
| 客户 | basic_info.customer[].name，非空时展示 |
| 项目 | basic_info.project_numbers[].name，非空时展示 |
| 备注 | basic_info.memo，非空时展示 |
| 说明 | basic_info.instruction，去除 HTML 标签后非空时展示 |
| 附件 | basic_info.attachments：**只展示"共 N 个"+ 各 title 列表**，**严禁输出 link 字段**（S3 预签名 URL 对用户无意义，污染聊天界面）。无附件则整行省略 |
| 关联邮件标题 | basic_info.related_emails：展示"共 N 个"+ 每个标题单独一行（超长标题完整输出，不截断）。数组为空则整行省略 |

**按需字段（默认不输出，仅当用户显式问"收件人/抄送/邮件分发/谁收到邮件"等相关问题时再展示）**：

| 展示字段 | 数据来源 |
|---------|---------|
| 收件人 | basic_info.email_tos：展示"共 N 个"+ 邮箱列表（每个邮箱一行，或用顿号分隔）。仅在用户问到时输出，日常"流程详情"查询**不展示** |
| 抄送人 | basic_info.email_ccs：展示"共 N 个"+ 邮箱列表。仅在用户问到时输出，日常"流程详情"查询**不展示** |

**合同信息展示规范**

若响应中 `contract_info` 非 null 且 `contract_info.list` 非空，则在流程基本信息表格后追加合同信息区块。

所属部门：`contract_info.department.name`（非空时展示）

合同列表以表格展示（每条合同一行），固定列：# | 合同编号 | 合同类型 | 主体 | 说明 | 签署方式 | 签字人；可选列（该列在所有合同中均无值则不展示）：客户 | 项目。

| 字段 | 数据来源 | 备注 |
|------|---------|------|
| 合同编号 | list[].contract_number | |
| 合同类型 | list[].type_name | |
| 主体 | list[].company.name | |
| 客户 | list[].customer.name | 可选列，所有行均为空则整列不展示 |
| 项目 | list[].project_no[].name，多个用顿号连接 | 可选列，所有行均为空则整列不展示 |
| 说明 | list[].instruction，去除 HTML 标签后，超过 30 字截断加「…」 | 为空则展示 - |
| 签署方式 | list[].sign_type | 0=空（展示 -），1=线上签署，2=线下签署，3=混合 |
| 签字人 | list[].need_sign_by[].name，多个用顿号连接 | 为空则展示 - |

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}" \

  'path_params={"mongo_id": "69a531074474d7dd34c67bd8"}'
```

---

## 第三步：查询当前审批任务详情（active_camunda_task_id 非空时必须查询）

`GET /v2/bpmn/process_instance/{mongo_id}/task/{task_id}`

task_id 取自上一步流程详情响应中的 `active_camunda_task_id` 字段。

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |
| task_id | string | 当前活动任务 ID（来自 active_camunda_task_id） |

**响应字段（关键字段，均在 `form` 对象下）**

| 字段 | 类型 | 说明 |
|------|------|------|
| form.task_id | string | 任务 ID |
| form.name | string | 审批节点名称（如"财务审核1"） |
| form.description | string | 审批节点描述 |
| form.type | string | 任务类型（如 `approval`） |
| form.assignees | array | 当前审批人列表（含 id 和 name） |
| form.can_handle | boolean | 当前用户是否可操作 |
| form.operator | string | 已操作人 ID（未操作时为空） |
| form.operator_name | string | 已操作人名称 |
| form.operate_time | string | 操作时间（UTC，展示转 UTC+8） |
| form.reason | string | 审批意见 |

**展示规范**

当前审批节点以加粗标题形式展示，格式：`**当前审批节点：{form.name}**`，下方列出当前审批人（form.assignees[].name），用顿号连接。**不展示任务类型。**

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/task/{task_id}" \

  'path_params={"mongo_id": "69a531074474d7dd34c67bd8", "task_id": "active-task-id"}'
```

---

## 第四步：用 mongo_id 探测资金数据（按需加载子文档）

**触发条件**：**只要走到本文档（无论用户说的是"流程详情""完整详情""流程信息"还是更泛的问法），第四步都是强制执行**。不存在"用户只问流程详情所以不跑第四步"的跳过理由。仅当三接口 `list` 全部为空时才"静默跳过展示"，但**接口调用本身必须做**。

反例（以下都是违规）：
- "用户只问流程详情，第 4 步属于资金数据，不跑" → ❌
- "判断为 2/3 步已满足用户意图，跳过第 4 步探测" → ❌
- "为节省 token，先不探测资金数据" → ❌

**业务互斥规则（关键）**：一个流程的资金数据**只会以三种形态之一出现**，互斥：
1. **资金业务**：资金信息 + 资金路径（两者通常成对出现）
2. **资金计划**：发起阶段的融资计划，独立存在
3. **合同业务**：合同信息（来自第二步流程详情的 `contract_info`），独立存在

**探测顺序（短路优先，命中即停）**：

1. **第一优先：资金信息 + 资金路径**。先并发调：
   - `GET /v2/bpmn/process_instance/{mongo_id}/fund_infos`
   - `GET /v2/bpmn/process_instance/{mongo_id}/fund_path/list`

   任一 `list` 非空 → 加载 `fund-data.md`，**只渲染资金信息 + 资金路径两块**，**跳过资金计划，跳过合同**（即使第二步响应里 `contract_info` 非空也不展示）。到此结束第四步，进第五步。

2. **第二优先：资金计划**。仅当第一步两接口**都为空**时执行：
   - `GET /v2/bpmn/process_instance/{mongo_id}/fund_plans`

   `list` 非空 → 加载 `fund-data.md`，**只渲染资金计划这一块**，**跳过合同**。到此结束第四步，进第五步。

3. **第三优先：合同**。仅当前两步全空时检查第二步流程详情响应里的 `contract_info.list`。非空 → 按第二步"合同信息展示规范"渲染合同块。

4. 若三者全空 → **不加载 `fund-data.md`**，不展示任何资金/合同块，直接进第五步。

**按需加载**：只有命中第 1 或第 2 档时才执行：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_plans" \
  'path_params={"mongo_id": "69a531074474d7dd34c67bd8"}'
```

---

### 资金路径列表

`GET /v2/bpmn/process_instance/{mongo_id}/fund_path/list`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |

**Query 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| task_id | string | 任务 ID |
| can_be_related | boolean | 是否可被关联 |
| version | string | 版本 |
| fund_change_prepare | string | 资金变更准备 |
| fund_change_draft_id | string | 资金变更草稿 ID |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 资金路径列表 |
| is_starter | boolean | 是否为发起人 |
| list[].status | string | 状态 |
| list[].type | string | 路径类型（如 `crypto_inbound`、`crypto_outbound`） |
| list[].transfer_type | string | 转账类型 |
| list[].memo | string | 备注 |
| list[].assignees | array | 执行人列表 |
| list[].achieved | boolean | 是否已完成 |
| list[].payment_deadline | string | 付款截止时间（纯日期，原样展示） |
| list[].fund_info.id | string | 关联资金信息 ID |
| list[].fund_path.status | string | 路径状态 |
| list[].fund_path.from.currency | string | 付款币种 |
| list[].fund_path.from.estimated_amount | string | 预估金额 |
| list[].fund_path.from.account.master_account_name | string | 付款方账户 |
| list[].fund_path.from.account.crypto_address | array | 付款方数字货币地址（含 address、network、address_tag） |
| list[].fund_path.from.platform.name | string | 付款平台 |
| list[].fund_path.from.name | string | 付款方名称（法人/对手方） |
| list[].fund_path.to.currency | string | 收款币种 |
| list[].fund_path.to.estimated_amount | string | 预估金额 |
| list[].fund_path.to.account.master_account_name | string | 收款方账户 |
| list[].fund_path.to.account.crypto_address | array | 收款方数字货币地址（含 address、network、address_tag） |
| list[].fund_path.to.platform.name | string | 收款平台 |
| list[].fund_path.to.name | string | 收款方名称（法人/对手方） |

**展示规范**

以表格展示，列顺序：# | 关联资金信息 | 状态 | 币种 | 预估金额 | 付款方账户 | 付款平台 | 收款方账户 | 收款平台 | 账户管理员 | 备注

其中：
- 关联资金信息 → 用 list[].fund_info.id 匹配资金信息列表中对应条目的序号，展示为"第N条"
- 账户管理员 → list[].assignees（字符串数组），多个用顿号连接，为空则展示 -
- 备注 → list[].memo，为空则展示 -

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_path/list" \
  'path_params={"mongo_id": "69a531074474d7dd34c67bd8"}' \
  'query_params={"task_id": "task-456"}'
```

---

## 第五步：审批历史（按需加载子文档）

**触发条件**：

- **路径 1（默认询问）**：前面四步完整输出后，追问一句：
  > 以上是流程完整详情。需要查看审批历史记录吗？

  用户明确同意 → 加载 `fund-approval-history.md` 并调用 `/tasks` 接口；
  用户拒绝/未回答 → 结束，**不加载**子文档。

- **路径 2（直接触发）**：用户在初始请求中直接说"审批历史 / 流程记录 / 审批记录"，跳过前四步，直接加载子文档。

- **反例**：用户说"走到哪了 / 走到哪个节点 / 当前审批节点" 查的是**当前**节点，走第三步 `/task/{task_id}`，**不要**加载本子文档，也不要调用 `/tasks`。

**加载**：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_infos" \
  'path_params={"mongo_id": "<mongo_id>"}' \
  'query_params={"version": "v1"}'
```

后续接口调用与展示规范以 `fund-approval-history.md` 为准。
