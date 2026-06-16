# 逻辑账户流水看板 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 依赖**：涉及业务线占用分析；先到父 skill `references/common-id-mapping.md` 取业务线字典。

## 逻辑账户流水看板

### 资产端概览

`GET /v1/v_flows/asset_side/overview`

> **使用场景**：用户询问"资产端概览"、"资产端流入流出"、"资产端业务线占用"时，直接调用此接口，**不要使用** `/v1/v_flows` 通用流水接口手动汇总。

含资金流向、业务线占用、流入流出概览。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_flows/asset_side/overview" \
  'query_params={"start_date": "2024-01-01", "end_date": "2024-12-31", "currency": "USDT"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| start_date | string | 统计开始日期 |
| end_date | string | 统计结束日期 |
| currency | string | 币种列表 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| asset_biz_headers | object | 资产端占用的币种 header |
| distributions | array | 资产端占用的币种分布 |
| flow_bars | array | 资产端流入流出概览（柱状图） |
| flows | array | 流水数据 |
| fund_change_currency_headers | object | 资产端资金变动的币种 header |
| fund_change_records | array | 资产端资金变动记录 |
| last_update_time | string | 数据最近更新时间（UTC，展示转 UTC+8） |
| occupied | object | 占用数据 |
| top10_distributions | array | 资产端占用的币种 top10 分布 |

---

### 资金端资产占用分布（全量）

`GET /v1/v_flows/fund_side/asset_distribution`

> **使用场景**：用户询问"资金端资产分布"、"资金端占用分布"、"截至某日的资金端余额分布"时，直接调用此接口，**不要使用** `/v1/v_flows` 通用流水接口手动汇总。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_flows/fund_side/asset_distribution" \
  'query_params={"currency": "USDT", "end_date": "2024-12-31"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| currency | string | 币种列表 |
| end_date | string | 统计结束日期 |
| is_all | bool | 是否全部业务线 |
| is_flow_data | bool | 是否为流程数据 |
| expected_fund_tag_id | string | 理论资金来源 ID 列表 |
| fund_tag_id | string | 实际资金来源 ID 列表 |
| fund_transfer_time_start | string | 出入账时间-开始 |
| fund_transfer_time_end | string | 出入账时间-结束 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| asset_headers | object | 资产端表头 |
| currency_sub_headers | object | 币种子表头（选择币种时有值） |
| distributions | array | 资产占用分布 |
| last_update_time | string | 数据最近更新时间（UTC，展示转 UTC+8） |

---

### 资金端概览

`GET /v1/v_flows/fund_side/overview`

> **使用场景**：用户询问"资金端概览"、"资金池变动"、"资金端业务线占用分析"时，直接调用此接口，**不要使用** `/v1/v_flows` 通用流水接口手动汇总。

含资金池变动、分布概览、业务线占用分析。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_flows/fund_side/overview" \
  'query_params={"start_date": "2024-01-01", "end_date": "2024-12-31", "currency": "USDT"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| start_date | string | 统计开始日期 |
| end_date | string | 统计结束日期 |
| currency | string | 币种列表 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| distributions | array | 资金池的币种分布 |
| flows | array | 流水数据 |
| fund_biz_headers | object | 资金池的业务线 header |
| last_update_time | string | 数据最近更新时间（UTC，展示转 UTC+8） |
| occupied | object | 占用数据 |
| top10_distributions | array | 资金池的币种 top10 分布 |

---

### 资金端本金看板（币种维度）

`GET /v1/v_flows/fund_side/principal`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/v_flows/fund_side/principal" \
  'query_params={"end_date": "2024-12-31"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| end_date | string | 统计结束日期 |
| is_flow_data | bool | 是否为流程数据 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| currency_headers | object | 币种表头 |
| distributions | array | 本金占用币种的分布 |
| last_update_time | string | 数据最近更新时间（UTC，展示转 UTC+8） |
