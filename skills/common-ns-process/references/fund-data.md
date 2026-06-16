# 资金数据（资金计划 / 资金信息 / 资金路径）参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #1**：本文档由 fund.md 第四步按短路优先级命中后加载；入口流程见父 skill `references/common-query-chains.md#链-1`。

> **前置假设**：本文档由 `fund.md` 第四步按**短路优先级**命中后按需加载。调用方已持有 `instance_id` 及所需接口的原始响应；本文档只规定**字段映射与展示格式**，不再负责接口调用或互斥判定。
>
> **业务形态互斥**：一个流程只会落在三种形态之一 —— ①资金业务（资金信息+资金路径成对）②资金计划 ③合同业务。**互斥判定由 `fund.md` 第四步完成**，本文档只渲染被 `fund.md` 指定的那一块。
>
> **展示顺序**：
> - 命中资金业务时，渲染顺序固定为 **资金信息 → 资金路径**（资金信息先于资金路径，便于资金路径"关联资金信息：第N条"展示时用户先看到被关联的主表）。本场景下**不渲染资金计划**，即使 `fund_plans.list` 非空也忽略。
> - 命中资金计划时，**只渲染资金计划**，不展示资金信息、资金路径。

---

## 资金计划列表

`GET /v2/bpmn/process_instance/{mongo_id}/fund_plans`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 资金计划列表 |
| list[].coin | string | 币种 |
| list[].amount | string | 金额 |
| list[].fund_type | int | 资金类型（1=出资） |
| list[].business_line.name | string | 业务线 |
| list[].business_contacts | array | 业务联系人列表（含 id、name） |
| list[].fund_tag.name | string | 实际资金标签 |
| list[].expected_fund_tag.name | string | 理论资金标签 |
| list[].expected_payment_time | string | 预计付款时间（纯日期，原样展示） |
| list[].payment_deadline | string | 付款截止时间（纯日期，原样展示） |
| list[].expected_occupation_time | string | 预计占用时长 |
| list[].project_overview | string | 项目概述 |
| list[].urgency | int | 紧急程度（1=普通，2=紧急，3=非常紧急） |

**展示规范**

以表格展示，列顺序：# | 币种 | 金额 | 业务线 | 实际资金标签 | 理论资金标签 | 预计付款时间 | 付款截止时间 | 预计占用时长 | 紧急程度 | 业务联系人 | 项目概述

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_plans" \
  'path_params={"mongo_id": "<mongo_id>"}'
```

---

## 资金信息列表

`GET /v2/bpmn/process_instance/{mongo_id}/fund_infos`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |

**Query 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| version | string | 版本 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 资金信息列表 |
| list[].activity.name | string | 行为 |
| list[].currency | string | 币种 |
| list[].amount | string | 金额 |
| list[].from.name | string | 来源方 |
| list[].from_type | int | 来源方类型（2=主体，4=业务线） |
| list[].to.name | string | 目标方 |
| list[].to_type | int | 目标方类型（2=主体，4=业务线） |
| list[].transaction_header.name | string | 业务表名称 |
| list[].fund_tag.name | string | 资金标签 |
| list[].expected_fund_tag.name | string | 预期资金标签 |
| list[].project_number.name | string | 项目 |
| list[].status | string | 状态 |
| list[].index | string | 序号 |
| list[].subs | array | 子资金信息列表（兑换等拆分场景） |
| list[].subs[].activity.name | string | 子行为 |
| list[].subs[].currency | string | 子币种 |
| list[].subs[].amount | string | 子金额 |
| list[].subs[].from.name | string | 子来源方 |
| list[].subs[].to.name | string | 子目标方 |
| list[].subs[].transaction_header.name | string | 子业务表名称 |
| list[].subs[].fund_tag.name | string | 子实际资金标签 |
| list[].subs[].expected_fund_tag.name | string | 子理论资金标签 |

**展示规范**

以表格展示，列顺序：# | 行为 | 币种 | 金额 | 来源方 | 目标方 | 业务表名称 | 理论资金标签 | 实际资金标签

其中：
- 理论资金标签 → list[].expected_fund_tag.name
- 实际资金标签 → list[].fund_tag.name
- 若 list[].subs 非空，且 subs 中存在与父行 id 不同的条目，则展示这些子行，子行序号用 1-1、1-2 格式，字段同上，取自 subs[] 对应字段；若 subs 只有一条且 id 与父行相同，则为冗余数据，不展示

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_infos" \
  'path_params={"mongo_id": "<mongo_id>"}' \
  'query_params={"version": "v1"}'
```

---

## 资金路径列表

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
| list[].payment_deadline | string | 付款截止时间 |
| list[].fund_info.id | string | 关联资金信息 ID |
| list[].fund_path.status | string | 路径状态 |
| list[].fund_path.from.currency | string | 付款币种 |
| list[].fund_path.from.estimated_amount | string | 预估金额 |
| list[].fund_path.from.account.master_account_name | string | 付款方主账户 |
| list[].fund_path.from.account.sub_accounts | array | 付款方子账户列表（含 sub_account_name、estimated_amount）；非空时付款方为子账户集 |
| list[].fund_path.from.account.crypto_address | array | 付款方数字货币地址（含 address、network、address_tag） |
| list[].fund_path.from.platform.name | string | 付款平台 |
| list[].fund_path.from.name | string | 付款方名称（法人/对手方） |
| list[].fund_path.to.currency | string | 收款币种 |
| list[].fund_path.to.estimated_amount | string | 预估金额 |
| list[].fund_path.to.account.master_account_name | string | 收款方主账户 |
| list[].fund_path.to.account.sub_accounts | array | 收款方子账户列表（含 sub_account_name、estimated_amount）；非空时收款方为子账户集 |
| list[].fund_path.to.account.crypto_address | array | 收款方数字货币地址（含 address、network、address_tag） |
| list[].fund_path.to.platform.name | string | 收款平台 |
| list[].fund_path.to.name | string | 收款方名称（法人/对手方） |

**展示规范**

以表格展示，列顺序：# | 关联资金信息 | 状态 | 币种 | 预估金额 | 付款方账户 | 付款平台 | 收款方账户 | 收款平台 | 账户管理员 | 备注

其中：
- 关联资金信息 → 用 list[].fund_info.id 匹配资金信息列表中对应条目的序号，展示为"第N条"
- 付款方账户 / 收款方账户：
  - 若 `from.account.sub_accounts` / `to.account.sub_accounts` **非空数组** → 按子账户集展示，格式 `{master_account_name}（{sub_account_name}: {estimated_amount} / ...）`，多个子账户用 ` / ` 连接
  - 若 `sub_accounts` 为空数组或缺失 → 只展示 `master_account_name`
- 账户管理员 → list[].assignees（字符串数组），多个用顿号连接，为空则展示 -
- 备注 → list[].memo，为空则展示 -

**输出约束（防渲染崩坏）**：整张表必须**裸写**在正文（表格前后各空一行），**严禁用 ``` 代码块包住表格**（包住之后 Slack 会按等宽字体原样显示 `|` 分隔符，宽表会直接崩成若干断行）。资金信息主表、资金计划主表同此要求。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/fund_path/list" \
  'path_params={"mongo_id": "<mongo_id>"}' \
  'query_params={"task_id": "task-456"}'
```
