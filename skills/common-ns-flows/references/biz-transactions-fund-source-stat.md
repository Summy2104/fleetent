# 项目资金来源汇总（查本金）参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #2**：调用前必须先取 `transaction_header_id`，见父 skill `references/common-query-chains.md#链-2`。
> **🔧 渲染脚本**：响应中 `header` / `rows` 字段是 JSON 字符串（非数组）；资金标签列动辄 130+，多数为 null。**禁止把完整响应塞进 agent 上下文**，统一用 `scripts/render_fund_source_stat.py` 预渲染为 TSV。

## 触发场景

- 「查本金」「查 X 项目本金」
- 「查项目资金来源」「查 X 项目资金来源汇总」
- 「查实际资金来源」「查理论资金来源」

## 端点

`GET /v1/biz_transactions/stat`

返回三个子表：**收入** / **实际资金来源** / **理论资金来源**。

## 查询流程

> ⚠️ **严禁凭项目编号前缀猜表头名**：`DPPZ` 开头不等于 `DP/借贷` 表。
> ⚠️ **`/v1/projects` 的 `no` 参数是精确匹配**，需传完整项目号（含后缀，如 `DPPZ01406-Storm`）。

### Step 1：项目号 → 业务线 ID

用户给出项目编号，先查项目取其业务线：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/projects" \
  'query_params={"no": "DPPZ01406-Storm", "page_size": "5"}'
```

从响应取 `business_line_id` 和 `business_line_name`，例如 `1813912038659411981` / `NS-配资`。

### Step 2：业务线 ID → 关联业务表列表

用业务线 ID 查该业务线下的所有业务表：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers" \
  'query_params={"biz_line_id": "1813912038659411981", "page": 1, "page_size": "20"}'
```

从返回列表中取 `id` 和 `name`：

- **单个表** → 直接用该 `id`
- **多个表** → 向用户展示候选列表，询问选哪个
- **空列表** → 提示用户该业务线下暂无业务流水表

> ⚠️ **端点白名单**：`/v1/biz_transaction_headers`（列表接口，支持 `biz_line_id` 过滤）需在 ns-mcp 服务端白名单中开放，与 `/v1/biz_transaction_headers/keyword`（全量字典接口）是不同路径。

### Step 3：解析项目编号字段名

不同业务表的「项目编号」列位置不固定（可能是 `f1`、`f2` 等），必须动态查询：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/<id>" \
  > $OUTBOUND_DIR/fund-source/header-detail-{ts}.json
```

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_fund_source_stat.py \
  --input $OUTBOUND_DIR/fund-source/header-detail-{ts}.json \
  --resolve-field
```

输出即为 `filter` 中要用的字段名（如 `f1`）。

### Step 4：调 stat 接口 + 落盘

将上一步得到的字段名（如 `f1`）代入 filter：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "filter": "{\"data_type\":\"2\",\"<field_name>\":\"DPPZ01406-Storm\"}", "group_field_keys": "0,1,2"}' \
  > $OUTBOUND_DIR/fund-source/raw-{ts}.json
```

> ⚠️ **`<field_name>` 必须来自 Step 3 的脚本输出**，不能硬编码 `f1`。`filter` 的值是精确匹配，字段名传错或项目号不完整均会导致返回空；结果仍为空时先排查是否选错业务表（回 Step 2）。

### Step 5：渲染

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_fund_source_stat.py \
  --input $OUTBOUND_DIR/fund-source/raw-{ts}.json \
  --output $OUTBOUND_DIR/fund-source/report-{ts}.tsv
```

读 TSV 展示给用户（不加工数值、不重排列顺序）。

## 请求参数

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| transaction_header_id | string | 必填 | 表头 ID（从 keyword 接口匹配得到） |
| group_field_keys | string | 必填 | 分组维度：`"0,1"`=资金汇总（业务线+币种）；`"0,1,2"`=项目+币种维度（查本金推荐） |
| filter | string | 视场景 | JSON 字符串。项目维度查询时必传 `{"data_type":"2","<field_name>":"<项目编号>"}`，`<field_name>` 由 Step 3 脚本动态解析 |
| snapshot_date | string | 可选 | 快照日期 `YYYY-MM-DD`，仅用户明确指定才传 |
| archive_id | string | 可选 | 存档 ID |
| dp_type | string | 可选 | DP type |

### `filter` 字段格式

JSON 字符串，例：

```json
{"data_type":"2","f1":"x黄金002"}
```

- `data_type`：`"2"` = 项目维度筛选
- `<field_name>`：由 Step 3 脚本从业务表列定义动态解析，不同表的「项目编号」列位置不同，不能硬编码 `f1`
- 项目编号值：精确匹配，必须传 `/v1/projects` 返回的完整 `no` 字段（含后缀）

## 响应结构

```json
{
  "list": [
    {"title": "收入",         "header": "[\"项目编号\",\"币种\",\"收入\"]",        "rows": "[[...]]"},
    {"title": "实际资金来源", "header": "[\"项目编号\",\"币种\",\"实际资金来源汇总\",...]", "rows": "[[...]]"},
    {"title": "理论资金来源", "header": "[\"项目编号\",\"币种\",\"理论资金来源汇总\",...]", "rows": "[[...]]"}
  ]
}
```

`header` 和 `rows` 都是 **JSON 字符串**（非数组）；「实际资金来源」/「理论资金来源」表的列数可达 130+，绝大多数列在单项目查询下都为 null。

## 渲染脚本 `render_fund_source_stat.py`

**行为**：
- parse `list[i].header` / `list[i].rows`（JSON 字符串）
- 「收入」表：原样输出（不过滤）
- 「实际资金来源」/「理论资金来源」表：drop 整列全为 null 的列；保留 0 / 空字符串 / 其它非 null 值
- 输出 TSV，每个子表前一行 title，三表间空行分隔
- stdout 单行摘要：`项目资金来源汇总 | 收入(cols=N,rows=M) | 实际资金来源(cols=N,rows=M) | 理论资金来源(cols=N,rows=M)`

**调用（渲染模式）**：

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_fund_source_stat.py \
  --input <raw.json> --output <report.tsv>
```

**调用（字段解析模式）**：

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_fund_source_stat.py \
  --input <header_detail.json> --resolve-field
```

输出「项目编号」对应的 `field_name`（如 `f1`），供 Step 4 组装 filter 使用。

纯标准库，无外部依赖。

---

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 运行时（经 bash_exec）须替换为 Step 0（whoami）提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调 `armada__armada_*`**。规则见 `SKILL.md §调用模式`。
