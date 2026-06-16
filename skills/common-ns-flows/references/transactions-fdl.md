# FDL 结算 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

## FDL 结算（三步流程）

### 第一步：结算单月份列表

`GET /v1/fdl-settlements`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fdl-settlements" \
  'query_params={"page": 1, "page_size": 10}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 结算单列表（含 `id` 字段，供下一步使用） |
| page_info | object | 分页信息 |

---

### 第二步：结算单客户列表

`GET /v1/fdl-settlements/{settlement_id}/customers`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fdl-settlements/{settlement_id}/customers" \
  'path_params={"settlement_id": "fdl-001"}' \
  'query_params={"page": 1, "page_size": 20}'
```

**路径参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| settlement_id | string | 结算单 ID（来自第一步的 `id` 字段） |

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 客户列表（含 `id` 字段，供下一步使用） |
| page_info | object | 分页信息 |

---

### 第三步：客户详情

`GET /v1/fdl-settlements/{settlement_id}/customers/{customer_id}`

> **注意**：`id` 为必传查询参数，来自第二步客户列表中该客户记录的 `id` 字段（非 `customer_id`，两者不同）。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fdl-settlements/{settlement_id}/customers/{customer_id}" \
  'path_params={"settlement_id": "fdl-001", "customer_id": "cust-123"}' \
  'query_params={"id": "record-id-from-step2"}'
```

**路径参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| settlement_id | string | 结算单 ID |
| customer_id | string | 客户 ID（来自第二步列表的 `customer_id` 字段） |

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 结算单客户记录 ID（来自第二步列表的 `id` 字段，必填） |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| settlement_id | string | 结算单 ID |
| customer_id | string | 客户 ID |
| customer_name | string | 客户名称 |
| start_date | string | 期初日期 |
| end_date | string | 结算日期 |
| address_list | array | 客户-地址列表 |
| item_list | array | 客户-项目列表 |
