# 业务资金汇总表 端点索引

> **⚠️ 鉴权契约**：本文档所有示例命令均经内置 `bash_exec` 走 `common-ns-biz-fund-summary/scripts/ns-call.sh` wrapper，由 wrapper 注入 `_meta.slackUserId`。`"$UID"` 是占位符，agent 运行时替换为 Step 0（`whoami`）提取的真实 `sender_id`。**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`。

## 端点一览

| 端点 | 方法 | 说明 |
|------|------|------|
| `/v1/projects` | GET | 查项目信息（按项目号查业务线，用项目号筛选时必须先调） |
| `/v1/biz_transaction_headers/keyword` | GET | 表头名称字典（ID→名称，必须先调） |
| `/v1/biz_transaction_headers/{id}` | GET | 表头详情（查 filter 字段名，有筛选条件时调） |
| `/v1/biz_transactions/stat` | GET | 业务资金汇总 |

---

## 0. 查项目信息（按项目号查业务线）

`GET /v1/projects`

**用途**：用户以项目号为筛选条件时，先通过项目号查出所属业务线（`business_line_name`），再用业务线名称从表头字典中匹配业务表。

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/projects" \
  'query_params={"no": "<项目号>"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| no | string | 项目编号（如 `AssM00104-Xcoin`） |

**关键响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list[].id | string | 项目 ID |
| list[].no | string | 项目编号 |
| list[].business_line_id | string | 业务线 ID |
| list[].business_line_name | string | 业务线名称（用于后续匹配表头字典） |

**使用方式**：取 `business_line_name`，在表头字典（端点 1）返回的 `list[].name` 中模糊匹配，找到对应的业务表 `id`。

---

## 1. 表头名称字典

`GET /v1/biz_transaction_headers/keyword`

**用途**：取全量表头 id+name 列表，用于匹配用户提到的业务线/表名，获得 `transaction_header_id`。

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/keyword"
```

无请求参数。

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 表头列表 |
| list[].id | string | 表头 ID |
| list[].name | string | 表名称 |

---

## 2. 表头详情（查筛选字段名）

`GET /v1/biz_transaction_headers/{id}`

**用途**：查询表头列定义，从 `headers[]` 中找到用户筛选条件对应的 `field_name`（如 `f3`），用于构造 filter。**不同表字段名不同，严禁跨表复用。**

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/{id}" \
  'path_params={"id": "<transaction_header_id>"}'
```

**路径参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 表头 ID |

**关键响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| headers | array | 列定义列表 |
| headers[].name | string | 列中文名（如「项目编号」） |
| headers[].field_name | string | 列字段名（如 `f3`），用作 filter key |
| headers[].is_filter | bool | `true` 表示该列支持在 filter 中筛选 |

**使用方式**：找到 `name` 匹配的列，取其 `field_name` 拼入 filter，如 `{"data_type":"2","f3":"AssM00104-Xcoin"}`。

---

## 3. 业务资金汇总

`GET /v1/biz_transactions/stat`

**用途**：查询指定业务表在特定快照日期的资金汇总数据。

无筛选条件：
```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "snapshot_date": "YYYY-MM-DD", "group_field_keys": "0,1", "filter": "{\"data_type\":\"2\"}"}'
```

有筛选条件（以项目编号为例，`f3` 需从表头详情动态取得）：
```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "snapshot_date": "YYYY-MM-DD", "group_field_keys": "0,1", "filter": "{\"data_type\":\"2\",\"f3\":\"<项目编号>\"}"}'
```

**请求参数**

| 字段 | 类型 | 是否必填 | 说明 |
|------|------|---------|------|
| transaction_header_id | string | 必填 | 表头 ID（从 keyword 接口匹配得到，不得猜测） |
| snapshot_date | string | 条件必填 | 快照日期 `YYYY-MM-DD`；用户指定时间时必填，未指定时不传（返回当前最新数据） |
| group_field_keys | string | **固定必传** | 固定值 `"0,1"`，资金汇总维度 |
| filter | string | **固定必传** | 至少包含 `{"data_type":"2"}`（正式数据）；有筛选条件时追加动态字段，如 `{"data_type":"2","f3":"项目编号"}` |
| archive_id | string | 可选 | 存档 ID |
| dp_type | string | 可选 | DP type |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| header | object | 表头定义（含列名映射） |
| list | array | 汇总数据行 |
| rows | array | 原始数据行 |
