# 两步/多步查询链 playbook

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

很多用户表述自然，但 NS API **不支持直接按名字查**，必须先取 ID 再查目标资源。本文档集中记录所有两步/多步查询链，避免 skill 漏做前置步骤导致用错字段、查不到数据或误用 ID。

## 链 #1：流程编号 → instance_id → 资金/审批详情

**触发表述**：用户给的是 11 位流程编号（如 `20260410035`），要看资金计划/资金路径/资金信息/审批历史/流程节点。

**所属子 skill**：`common-ns-process`

### Step 1：流程编号 → instance_id

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/number/{process_number}" \
  'path_params={"process_number": "20260410035"}'
```

返回 `data.instance_id`。

### Step 2：按需求查目标资源

- 基本信息 + `active_camunda_task_id`：`GET /v2/bpmn/process_instance/{instance_id}`
- 资金计划：`GET /v2/bpmn/process_instance/{instance_id}/fund_plans`
- 资金路径：`GET /v2/bpmn/process_instance/{instance_id}/fund_path/list`
- 资金信息：`GET /v2/bpmn/process_instance/{instance_id}/fund_infos`
- 当前任务详情（走到哪个节点）：`GET /v2/bpmn/process_instance/{instance_id}/task/{task_id}`（task_id 取自基本信息的 `active_camunda_task_id`）
- 审批历史 / 流程记录：`GET /v2/bpmn/process_instance/{instance_id}/tasks`

具体字段映射见 `common-ns-process/references/fund.md`（入口）→ `fund-data.md` / `fund-approval-history.md`。

### 常见坑
- **`active_camunda_task_id` 必须来自本次 GET 实例详情的响应**；严禁用历史会话/记忆里的 task_id
- **审批历史**只在用户明确说"审批历史 / 流程记录 / 审批记录"时调用
- **fund_plans / fund_infos / fund_path 三类互斥**：一个流程只落在三种形态之一（资金业务 / 资金计划 / 合同业务），判定由 `fund.md` 第四步完成

---

## 链 #2：流程定义名 → mongo_id → 流程 XML / 审批配置

**触发表述**：用户想看某个流程的流程图 / 审批组配置（如"看一下 NS-Trading 付款流程的审批配置"）。

**所属子 skill**：`common-ns-process`

### Step 1：流程定义名 → mongo_id

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/process_definition/list" \
  'query_params={"exclude_draft": true, "keyword": "付款"}'
```

找到目标流程的 `mongo_id`（**不是** `id` 字段！`id` 在草稿态下为空，非草稿下格式也不同）。

### Step 2：查 XML 或审批配置

- 流程图 XML：`GET /v1/bpmn/process_definition/{mongo_id}/xml`
- 审批配置（审批组/审批短语）：其它相关 approval 接口，详见 `common-ns-process/references/business-config-process-approval.md`

### 常见坑
- 搞混 `id` 和 `mongo_id` 是最常见错误；每次一定核对请求用的是 `mongo_id`
- `exclude_draft=true` 建议加（避免草稿态流程污染列表）

---

## 链 #3：审批人姓名/邮箱 → approver_id → 流程看板筛选

**触发表述**：用户问"审批人是 XX 的流程"、"XX 审批过的"。

**所属子 skill**：`common-ns-process`

### Step 1：审批人 → approver_id

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/management/approver/list" \
  'query_params={"user_name": "Alice Wang"}'
```

或按邮箱：`'query_params={"user_email": "alice@nsdigital.io"}'`

### Step 2：流程看板按审批人筛

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/dashboard/all" \
  'query_params={"approver_id": "<id>"}'
```

### 常见坑
- `approver_id` 与用户 `user_id`、审批组 `approver_group_id` 不同，别混用
- 邮箱匹配大小写不敏感，但 `user_name` 是精确匹配（推荐用邮箱更稳）

---

## 链 #4：链名 + 币种名 → chain_id + coin_id → 数币账户筛选

**触发表述**：用户问"USDT on TRC20 的数币账户"、"ETH 链上的 xxx 白名单"。

**所属子 skill**：`common-ns-masterdata`

### Step 1：分别查链字典和币字典

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/nets"
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/mo"
```

在返回的 list 里按 name 找 `chain_id` 和 `coin_id`（注意这两个是**数字字符串 ID**，不是币种符号/链名本身）。

### Step 2：查数币账户（按条件）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  post "/v1/accounts/digital_coin" \
  'body={"chain_id": "<id>", "coin_id": "<id>", "page": 1, "page_size": 20}'
```

### 常见坑
- **`chain_id` / `coin_id` 必须是数字字符串 ID**，不能直接传链名（"TRC20"）或币种符号（"USDT"）
- 若 `coin_id` 未指定可以不传（省略字段）；若链不限同样可省

---

## 链 #5：业务线名 → biz_line → 项目筛选

**触发表述**：用户问"配资业务线下的项目"、"Trading 的项目列表"。

**所属子 skill**：`common-ns-masterdata`

### Step 1：业务线名 → biz_line（注意字段名）

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines/keyword"
```

### Step 2：按业务线 ID 查项目

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/projects" \
  'query_params={"biz_line": "<id>", "page": 1, "page_size": 20}'
```

### 常见坑
- ⚠️ 这里参数名是 **`biz_line`**（**非** `biz_line_id`），与其它端点不一致
- 客户列表接口是 `biz_line_ids`（数组）；流程看板是 `biz_line_id`（单数）——每次按端点 reference 确认

---

## 链尾的通用提醒

- 每条链的 Step 1 一般是**字典查询**（全量返回，本轮 turn 可缓存复用）
- Step 2 才是目标查询（分页的）
- **禁止跨链复用 ID**：`mongo_id` 不能当 `instance_id` 用，`approver_id` 不能当 `user_id` 用，等等
- 若 Step 1 返回空（找不到名字对应的 ID），立即停止并告知用户"未找到该名称对应的 ID"，**不要编造 ID**
