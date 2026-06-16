# 资金端流动性看板 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：筛选参数含 `biz_line_id` 或 `fund_type` 时，先到父 skill `references/common-id-mapping.md` 取字典。

## 资金端流动性看板

### `GET /v1/fund_dashboard` - 资金端流动性看板

> **使用场景**：用户询问"资金端流动性"、"流动性看板"、"资金流动性"、"查看某类资金的流动性数据"时，调用此接口获取资金余额汇总。同时需配合 `/v1/process_transactions`（流程流水列表）和 `/v1/process_transactions/summary`（流程流水汇总）展示完整看板，均通过 `fund_type` 参数筛选对应资金类型。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fund_dashboard" \
  'query_params={"fund_type": 1}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| fund_type | int | 资金类型（见下方枚举值） |

**fund_type 枚举值**

| 值 | 名称 | 资金标签 |
|----|------|---------|
| 1 | FUND_TYPE_XYJD | AZ01 |
| 2 | FUND_TYPE_XYJDFDL | AY01 |
| 3 | FUND_TYPE_ZYJDW | BX01（非Mining） |
| 4 | FUND_TYPE_NS | EV01 |
| 5 | FUND_TYPE_BM | AZ05 |
| 6 | FUND_TYPE_ZYWK | CV01 |
| 7 | FUND_TYPE_ZYJDN | BW01 |
| 8 | FUND_TYPE_XYJD_DQ | AZ02&AZ03 |
| 9 | FUND_TYPE_ZYJDW_MINING | BX01（Mining） |
| 10 | FUND_TYPE_HJJDW | BX02 |
| 11 | FUND_TYPE_SLLC | 算力理财 |
| 12 | FUND_TYPE_DLKC_NR2 | CV03（NR2） |
| 13 | FUND_TYPE_DLKC_ND1 | CV03（ND1） |
| 14 | FUND_TYPE_DLKC_ND2 | CV03（ND2） |
| 15 | FUND_TYPE_TSZJ | EV02 |
| 16 | FUND_TYPE_DLKC_MV | CV03（MV） |
| 17 | FUND_TYPE_BM_JD | AZ04 |
| 18 | FUND_TYPE_DLKC_MURPHY | CV03（murphy） |
| 19 | FUND_TYPE_ZYWK_JIEKUAN | CV01_02 |
| 20 | FUND_TYPE_NS_AY01 | EV01_AY01 |
| 21 | FUND_TYPE_PCL | PCL未明确资金 |
| 22 | FUND_TYPE_LENDING_PROFIT | BW02 |
| 23 | FUND_TYPE_XAUE_BX04 | BX04 |

**响应字段**

顶层结构：`fund_summary`（列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| coin | string | 币种 |
| fund_pool_amount | string | 资金池账户余额 |
| dp_flow_amount | string | DP 流动性管理余额 |
| mining_flow_amount | string | 挖矿流入金额 |
| other_flow_amount | string | 其他流入金额 |
| summary_amount | string | 合计 |

**展示规范**

以表格展示，列顺序：币种 | 资金池账户余额 | DP 流动性管理余额 | 合计

其中：空字符串字段展示为 `-`；**数值字段必须原样输出 API 返回的完整字符串，禁止四舍五入或截断小数位**。

---

### `GET /v1/process_transactions` - 流程流水列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/process_transactions" \
  'query_params={"fund_type": 4, "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| fund_type | int | 资金类型（枚举值同上） |
| process_name | string | 流程名称 |
| process_instance_id | string | 流程 ID |
| coin | string | 币种 |
| from_account_id | string | 付款账户 ID |
| to_account_id | string | 收款账户 ID |
| txid | string | TXID |
| process_instance_start_time_start | string | 发起时间-开始 |
| process_instance_start_time_end | string | 发起时间-结束 |
| process_instance_end_time_start | string | 完成时间-开始 |
| process_instance_end_time_end | string | 完成时间-结束 |
| type | int | 流水类型：1=手动，2=自动，3=导入，4=同步 |
| project_no | string | 项目编号 |
| has_related_transactions | int | 有无业务表记录：`0`=不过滤，`1`=有关联记录，`2`=无关联记录 |
| from_account_owner_id | string | 付款客户 ID |
| to_account_owner_id | string | 收款客户 ID |
| id | string | 流水 ID |
| business_line_id | string | 业务线 ID |
| process_instance_number | string | 流程编号（精确匹配，传字符串） |
| from_address | string | 付款地址 |
| to_address | string | 收款地址 |
| account_owner_id | string | 付款方/收款方 ID |
| import_status | int | 导入状态：1=生效，2=未生效 |
| email_title | string | 邮件标题 |
| amount | string | 数量 |
| from_account_owner_ids | string | 付款方 IDs |
| to_account_owner_ids | string | 收款方 IDs |
| account_id | string | 账户 ID |
| process_instance_transfer_time_start | string | 动账开始时间 |
| process_instance_transfer_time_end | string | 动账结束时间 |
| is_allow_query_privacy | bool | 是否允许查询隐私流程 |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

顶层结构：`list`（流水列表）、`page_info`（分页信息）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| id | string | 流水 ID |
| process_instance_number | string | 流程编号 |
| process_instance.id | string | 流程实例 ID |
| process_instance.name | string | 流程名称 |
| process_instance_start_time | string | 流程发起时间（UTC，展示转 UTC+8） |
| process_instance_end_time | string | 流程完成时间（UTC，展示转 UTC+8） |
| transfer_time | string | 动账时间（UTC，展示转 UTC+8） |
| coin | string | 币种 |
| amount | string | 金额 |
| from | string | 付款方名称 |
| from_account_name | string | 付款账户名称 |
| from_platform_name | string | 付款平台 |
| from_address_name | string | 付款地址 |
| to | string | 收款方名称 |
| to_account_name | string | 收款账户名称 |
| to_platform_name | string | 收款平台 |
| to_address_name | string | 收款地址 |
| to_reference | string | 收款参考 |
| network | string | 链网络 |
| txid | string | 交易 ID |
| type | int | 流水类型：1=手动，2=自动，3=导入，4=同步 |
| import_status | int | 导入状态：1=生效，2=未生效 |
| email_title | string | 邮件标题 |
| business_line | array | 业务线列表（含 id、name） |
| project_no | array | 项目编号列表 |
| fund_tags | array | 资金标签列表（含 amount、fund_tag_name、expected_fund_tag_name） |
| related_transactions | array | 关联业务表记录（含 transaction_header_name、transaction_row_id） |
| fee_amount | string | 手续费金额 |
| fee_coin | string | 手续费币种 |
| settlement_amount | string | 结算金额 |
| settlement_currency | string | 结算币种 |
| created_at | string | 创建时间（UTC，展示转 UTC+8） |
| updated_at | string | 更新时间（UTC，展示转 UTC+8） |

**展示规范**

每条流水以竖向键值对表格展示（属性｜值），字段顺序：流水ID | 流程编号 | 邮件标题 | 币种 | 金额 | 付款方 | 付款账户 | 付款平台 | 付款地址 | 收款方 | 收款账户 | 收款平台 | 收款地址 | 收款参考 | 链网络 | TXID | 动账时间 | 流程发起时间 | 流程完成时间 | 流水类型 | 导入状态 | 业务线 | 项目编号 | 手续费金额 | 手续费币种 | 结算金额 | 结算币种 | 创建时间

其中：
- 流水类型：1=手动，2=自动，3=导入，4=同步
- 导入状态：1=生效，2=未生效
- 业务线：business_line[].name，多个用顿号连接
- 项目编号：project_no[]，过滤空字符串后多个用顿号连接，全空则展示 -
- 空字符串字段展示为 `-`
- 多条流水之间用分隔线隔开

---

### `GET /v1/process_transactions/summary` - 流程流水汇总

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/process_transactions/summary" \
  'query_params={"fund_type": 4}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|--------|------|------|
| fund_type | int | 资金类型（枚举值同上） |
| account_id | string | 付款方/收款方账户 ID |
| email_title | string | 邮件标题 |
| amount | string | 数量 |
| coin | string | 币种 |
| project_no | string | 项目编号 |
| process_instance_transfer_time_start | string | 动账开始时间 |
| process_instance_transfer_time_end | string | 动账结束时间 |

**响应字段**

顶层结构：`items`（列表）

| 字段名 | 类型 | 说明 |
|--------|------|------|
| coin | string | 币种 |
| receive_amount | string | 资金池账户收款金额 |
| pay_amount | string | 资金池账户付款金额 |
| net_amount | string | 资金池账户净入账金额 |

**展示规范**

以表格展示，列顺序：币种 | 资金池账户收款金额 | 资金池账户付款金额 | 资金池账户净入账金额
