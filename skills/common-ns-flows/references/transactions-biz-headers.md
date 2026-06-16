# 业务流水与表头 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #2**：业务流水列表/统计前必须先取 transaction_header_id，见父 skill `references/common-query-chains.md#链-2`。业务线筛选字段 `biz_line_id` 见 `references/common-id-mapping.md#业务线字段名陷阱`。
> **🔧 渲染脚本**：响应 `rows` 字段是 JSON 字符串；推荐用 `scripts/render_biz_transactions.py` 预渲染为 TSV 后再展示。

## 业务流水列表

`GET /v1/biz_transactions`

> ⚠️ **当前 skill 版本能力范围**：
> - **入口**：只支持按**业务线**或**业务表名**查询（查到表头 ID 后调此接口）
> - **分页**：固定 `page=1, page_size=50`，只展示前 50 条；用户要求看更多时，提示"当前版本仅展示前 50 条，更多数据请使用业务表前端界面"
> - **筛选**：**暂不支持** `filter` / `sort` / `row_ids` / `dp_type` 等参数，即使用户明确要求按条件筛选也拒绝并提示"当前版本不支持筛选，后续会补上"
> - **仅支持参数**：`transaction_header_id`（必填）、`page`、`page_size`、`snapshot_date`（可选）

### 查询流程

1. 调 `GET /v1/biz_transaction_headers/keyword` 获取全量表头 id+name 列表
2. 按用户提到的**业务线**或**表名**匹配：
   - **单个匹配** → 直接用该 id 调此接口
   - **多个匹配** → 向用户展示候选表名列表，询问选哪个
   - **无匹配** → 提示用户确认业务线或表名
3. 用匹配到的 `transaction_header_id` 调此接口，**固定传** `page=1, page_size=50`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions" \
  'query_params={"transaction_header_id": "xxx", "page": 1, "page_size": 50}'
```

**允许传递的请求参数**

| 字段 | 类型 | 是否必填 | 说明 |
|------|------|---------|------|
| transaction_header_id | string | 必填 | 表头 ID（从 keyword 接口匹配得到） |
| page | int | 固定 | 固定传 `1` |
| page_size | int | 固定 | 固定传 `50` |
| snapshot_date | string | 可选 | 快照日期 `YYYY-MM-DD`；用户明确指定日期时才传 |

**禁止传递的参数**（当前 skill 版本不支持）：`filter`、`sort`、`row_ids`、`archive_id`、`dp_type`

### 渲染：走脚本，不要让 agent 手动解析

响应的 `header` 字段很大（一个枚举字段可能带 150+ 候选值），**禁止把完整响应塞进 agent 上下文**。固定流程：

1. 调接口后把原始响应写到 outbound 临时文件：
   ```bash
   bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
     get "/v1/biz_transactions" \
     'query_params={"transaction_header_id": "<id>", "page": 1, "page_size": 50}' \
     > $OUTBOUND_DIR/biz-txn/raw-{ts}.json
   ```
2. 跑渲染脚本（输出 TSV）：
   ```bash
   python3 $SKILLS_DIR/common-ns-system-query/scripts/render_biz_transactions.py \
     --input $OUTBOUND_DIR/biz-txn/raw-{ts}.json \
     --output $OUTBOUND_DIR/biz-txn/report-{ts}.tsv \
     --table-name "<匹配到的表头名>" \
     --max-rows 50
   ```
3. 脚本 stdout 输出一行摘要 `{表名} | total=N | shown=M | cols=K`
4. 读 `report-{ts}.tsv` 内容（制表符分隔），展示时可转 markdown 表格或原样发送，**agent 不加工数值、不重排列顺序**

脚本内部处理：
- parse `rows` 字符串 → 对象数组
- 按 header 的 `field_name → name` 映射展示列名
- 枚举值（`attr_id ∈ {6, 7}`）按 header 的 `attr_value` 把 id 映射回 name
- 丢弃 `is_used=false` 的列
- 丢弃本批次**所有行都为空**的列
- 按 header 的 `sort` 升序排列
- `email_title` 长于 60 字符自动截断为前 60 + "…"
- 日期字段（`attr_id=4`）格式化为 `YYYY-MM-DD HH:MM:SS`

---

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

## 业务流水资金汇总

`GET /v1/biz_transactions/stat`

> **查询前置步骤**：`transaction_header_id` 为实际必填，不得直接调用此接口。执行流程：
> 1. 先调用 `GET /v1/biz_transaction_headers/keyword` 获取全量表头 id+name 列表
> 2. 按用户提到的业务线/表名匹配：
>    - **单个匹配**：直接以该 `id` 调用 stat，`group_field_keys` 默认传 `"0,1"`
>    - **多个匹配**：向用户展示候选列表，询问选哪个后再调用
>    - **无匹配**：提示用户确认业务线或表头名称

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "xxx", "snapshot_date": "2024-12-31", "group_field_keys": "0,1"}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| transaction_header_id | string | 表头 ID |
| snapshot_date | string | 快照日期 |
| filter | string | 筛选条件 |
| archive_id | string | 存档 ID |
| group_field_keys | string | 分组 key：`0,1`=资金汇总；`0,1,2`=项目资金汇总 |
| dp_type | string | DP type |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| header | object | 表头 |
| list | array | 列表 |
| rows | array | 数据行 |

---

## 业务流水表头

### 表头详情

`GET /v1/biz_transaction_headers/{id}`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/{id}" \
  'path_params={"id": "header-123"}' \
  'query_params={"snapshot_date": "2024-12-31"}'
```

**路径参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 表头 ID |

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| fill_behavior_field | bool | 是否填充流水行为字段 |
| type | int | 类型：`1`=普通表，`2`=宽表 |
| snapshot_date | string | 快照日期 |
| archive_id | string | 存档 ID |
| only_enabled_behavior | bool | 是否只返回启用的流水行为 |
| biz_line_id | string | 业务线 ID |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 表头 ID |
| name | string | 表名称 |
| biz_line | object | 业务线信息 |
| company | object | 公司主体信息 |
| behaviors | array | 流水行为列表 |
| financial_infos | array | 财务会计信息 |
| headers | array | 表头列 |
| is_archived | bool | 是否已归档 |
| is_wide | bool | 是否宽表 |

---

### 表头关联行为列表

`GET /v1/biz_transaction_headers/{id}/behavior_keyword`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/{id}/behavior_keyword" \
  'path_params={"id": "header-123"}'
```

**路径参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 表头 ID |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 行为关键词列表 |

---

### 资金标签列表

`GET /v1/biz_transaction_headers/fund_mark`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/fund_mark" \
  'query_params={"name": "资金标签名", "status": 1, "page": 1, "page_size": 20}'
```

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| name | string | 名称（模糊搜索） |
| status | int | 状态：`1`=启用，`2`=禁用 |
| page | int | 页码 |
| page_size | int | 每页数量 |
| StatDate | string | 统计日期 |
| fund_tag_type | int | 标签类型：`1`=本金，`2`=客户资金，`3`=质押金，`4`=自营挖矿，`5`=资产，`6`=未明确资金 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 资金标签列表，见下方列表项说明 |
| page_info | object | 分页信息 |

列表项字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | string | 资金标签 ID |
| name | string | 名称 |
| status | int | 状态：`1`=启用，`2`=禁用 |
| fund_tag_type | int | 标签类型：`1`=本金，`2`=客户资金，`3`=质押金，`4`=自营挖矿，`5`=资产，`6`=未明确资金 |
| currency_type | int | 币种类型 |
| origin_name | string | 原始名称 |
| biz_lines | array | 业务线列表 |
| biz_line_rule | array | 业务线规则 |
| created_at | string | 创建时间（UTC，展示转 UTC+8） |

---

### 表头名称列表（ID 查名称）

`GET /v1/biz_transaction_headers/keyword`

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/biz_transaction_headers/keyword"
```

无请求参数。

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list | array | 表头名称列表 |
