# 实际交易流水与对账 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：涉及 bank / account 等跨 masterdata 的 ID；如需 bank/account 名称翻译见父 skill `references/common-id-mapping.md`。

## 实际交易流水

`GET /v1/r_transactions`

`process_status`：`completed`=查已完成表，`uncompleted`=查实时表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/r_transactions" \
  'query_params={"process_status": "completed", "project_no": "PRJ-001", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | ID |
| process_instance_number | string | 流程编号 |
| project_no | string | 项目号名称 |
| account_name | string | 账户名称 |
| fiat_number | string | 法币账户号或数币地址 |
| crypto_address | string | 数币地址 |
| business_line_id | string | 业务线 ID |
| network | string | 网络 |
| currency | string | 币种 |
| amount_min | string | 数量最小值 |
| amount_max | string | 数量最大值 |
| bank_id | string | 银行 ID（合并 from/to） |
| fee_coin | string | 手续费币种 |
| fee_amount_min | string | 手续费金额最小值 |
| fee_amount_max | string | 手续费金额最大值 |
| txid | string | 交易 ID |
| participant_type | int | 收付款方类型：`1`=公司，`2`=客户 |
| participant_id | string | 收付款方 ID |
| coin_type | int | 平台类型：`1`=数币，`2`=法币 |
| platform | string | 平台名称（合并 from/to） |
| fund_path_type | string | 流水类型：`crypto_inbound`=数币入账，`crypto_outbound`=数币出账，`fiat_inbound`=法币入账，`fiat_outbound`=法币出账 |
| email_title | string | 邮件标题 |
| activity_id | string | 行为 ID |
| deprecated_status | int | 作废状态：`1`=正常，`2`=删除 |
| expected_fund_tag_id | string | 理论资金来源 ID |
| fund_tag_id | string | 实际资金来源 ID |
| process_instance_fund_path_id | string | 资金路径 ID |
| updated_time_start | string | 更新时间-开始 |
| updated_time_end | string | 更新时间-结束 |
| transfer_time_start | string | 出入账时间-开始 |
| transfer_time_end | string | 出入账时间-结束 |
| v_transaction_id | string | 逻辑交易流水 ID |
| is_exceeded_limit | bool | 是否超出限制 |
| is_allow_query_privacy | bool | 是否允许查询隐私流程 |
| process_status | string | 流程状态：`completed`=已完成表，`uncompleted`=实时表 |
| sort | string | 排序 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 实际交易流水列表 |
| page_info | object | 分页信息 |

---

## 对账

`match_status` 枚举：`1`=已匹配/完全匹配，`2`=未匹配，`3`=已忽略，`4`=部分匹配，不传=全部

### NS 动账流水

`GET /v1/reconciliation/adjustment/real_transactions/r_flows`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/reconciliation/adjustment/real_transactions/r_flows" \
  'query_params={"match_status": 2, "transfer_time_start": "2024-01-01", "transfer_time_end": "2024-12-31", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| ns_id | string | NS 动账流水 ID |
| transfer_time_start | string | 出入账时间-开始 |
| transfer_time_end | string | 出入账时间-结束 |
| match_status | int | 匹配状态（支持多选）：`1`=已匹配，`2`=未匹配，`3`=已忽略，`4`=部分匹配 |
| linked_on | string | 匹配原因 |
| ignore_status | int | 忽略状态：`1`=正常，`2`=已忽略 |
| excluded_reason | string | 忽略原因 |
| market_name | string | 平台/交易所名称 |
| bank_id | string | 银行 ID |
| account_entity_id | string | 主体/客户 ID |
| account_id | string | 账户 ID |
| fiat_number | string | 法币账户号码 |
| crypto_address | string | 数币地址 |
| counterparty_account_id | string | 对手方账户 ID |
| counterparty_fiat_number | string | 对手方法币账户号码 |
| counterparty_crypto_address | string | 对手方数币地址 |
| coin | string | 币种名称 |
| amount_min | string | 数量最小值 |
| amount_max | string | 数量最大值 |
| network | string | 网络名称 |
| tx_id | string | TX ID |
| counterparty_market_name | string | 对手方平台 |
| counterparty_bank_id | string | 对手方银行 ID |
| counterparty_account_entity_id | string | 对手方主体/客户 ID |
| process_instance_number | string | 流程编号 |
| business_line_id | string | 业务线 ID |
| project_no | string | 项目号名称 |
| activity_id | string | 行为 ID |
| expected_fund_tag_id | string | 理论资金来源 ID |
| fund_tag_id | string | 实际资金来源 ID |
| email_title | string | 邮件标题 |
| middle_id | string | 中台动账 ID |
| v_transaction_id | string | 逻辑流水 ID |
| r_transaction_id | string | 实际流水 ID |
| updated_time_start | string | 更新时间-开始 |
| updated_time_end | string | 更新时间-结束 |
| deprecated_status | int | 作废状态：`1`=正常，`2`=已作废 |
| amount | string | 金额 |
| account_type | int | 账户类型：`1`=数币，`2`=法币 |
| process_instance_id | string | 流程实例 ID |
| coin_type | int | 币种类型：`1`=数币，`2`=法币 |
| address_tag | string | 地址标签 |
| is_allow_query_privacy | bool | 是否允许查询隐私流程 |
| remaining_matching_quantity | string | 剩余匹配数量 |
| flow_direction | int | 流向：`1`=入账，`2`=出账 |
| sort | string | 排序 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | NS 动账流水列表 |
| page_info | object | 分页信息 |

---

### 数币账户余额

`GET /v1/reconciliation/adjustment/account_balance`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/reconciliation/adjustment/account_balance" \
  'query_params={"account_id": "123", "coin": "USDT"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | string | 账户 ID |
| coin | string | 币种 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| account_id | string | 账户 ID |
| account_name | string | 账户名称 |
| list | array | 账户余额列表 |

---

### 中台动账流水

`GET /v1/reconciliation/middle_account/transactions`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/reconciliation/middle_account/transactions" \
  'query_params={"match_status": 2, "transfer_time_start": "2024-01-01", "transfer_time_end": "2024-12-31", "page": 1, "page_size": 20}'
```

**请求参数**

在 NS 动账流水参数基础上，额外支持：

| 字段 | 类型 | 说明 |
|------|------|------|
| middle_id | string | 中台动账 ID |
| excluded_reason | int | 忽略原因（中台专用）：`1`=其他，`2`=客户账户流水，`3`=Swap 兑换，`4`=转账金额手续费金额全部匹配，`5`=手续费，`6`=NS 系统已记录，`7`=重复流水，`8`=内部转账，`9`=不属于 NS 管理范围，`10`=已在其他系统处理，`99`=暂时忽略 |

其余参数同 NS 动账流水，请参考上方表格。

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 中台动账流水列表 |
| page_info | object | 分页信息 |
