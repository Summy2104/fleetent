# 逻辑交易流水与逻辑账户流水 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：筛选参数含 `biz_line_id` 时，先到父 skill `references/common-id-mapping.md` 取业务线字典。

## 逻辑交易流水

`GET /v1/v_transactions`

`process_status`：`completed`=查已完成表，`uncompleted`=查实时表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_transactions" \
  'query_params={"process_status": "completed", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| process_instance_id | string | 流程 ID |
| project_no | string | 项目号 |
| business_line_or_customer_id | string | 业务线 ID 或客户 ID |
| process_status | string | 流程状态：`completed`=已完成表，`uncompleted`=实时表 |
| process_instance_number | string | 流程编号 |
| fund_info_id | string | 资金信息 ID |
| activity_id | string | 行为 ID |
| expected_fund_tag_id | string | 理论资金来源 ID 列表 |
| fund_tag_id | string | 实际资金来源 ID 列表 |
| currency | string | 币种 |
| amount | string | 数量 |
| amount_min | string | 最小数量 |
| amount_max | string | 最大数量 |
| fund_transfer_time_start | string | 出入账时间-开始 |
| fund_transfer_time_end | string | 出入账时间-结束 |
| participant_id | string | 收付款方 ID |
| sort | string | 排序，支持 `id`/`fund_transfer_time`/`updated_at`/`amount`，默认 `fund_transfer_time desc` |
| id | string | ID |
| deprecated_status | int | 状态：`1`=正常，`2`=删除 |
| is_flow_data | bool | 是否为流程数据 |
| is_allow_query_privacy | bool | 是否允许查询隐私流程 |
| exclude_activity_ids | array | 排除行为 ID 列表 |
| page | int | 页码 |
| page_size | int | 每页数量 |
| is_exceeded_limit | bool | 是否超出限制 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 逻辑交易流水列表 |
| page_info | object | 分页信息 |

---

## 逻辑账户流水

`GET /v1/v_flows`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_flows" \
  'query_params={"project_no": "PRJ-001", "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 流水 ID |
| process_instance_number | string | 流程编号 |
| from_id | string | 客户或业务线 ID |
| to_id | string | 对手方 ID |
| flow_type | string | 流水类型 |
| project_no | string | 项目号 |
| activity_id | string | 行为 ID |
| currency | string | 币种 |
| amount_min | string | 数量最小值 |
| amount_max | string | 数量最大值 |
| fund_tag_id | string | 实际资金来源 ID 列表 |
| expected_fund_tag_id | string | 理论资金来源 ID 列表 |
| fund_transfer_time_start | string | 出入账时间-开始 |
| fund_transfer_time_end | string | 出入账时间-结束 |
| v_transaction_id | string | 逻辑交易流水 ID |
| deprecated_status | int | 是否排除在余额计算之外：`1`=正常，`2`=删除 |
| sort | string | 排序 |
| data_status | int | 状态：`1`=正常，`2`=已忽略 |
| is_flow_data | bool | 是否为流程数据 |
| is_allow_query_privacy | bool | 是否允许查询隐私流程 |
| exclude_activity_ids | array | 排除行为 ID 列表 |
| page | int | 页码 |
| page_size | int | 每页数量 |
| is_exceeded_limit | bool | 是否超出限制 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 逻辑账户流水列表 |
| page_info | object | 分页信息 |
