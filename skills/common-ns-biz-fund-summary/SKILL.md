---
name: common-ns-biz-fund-summary
description: >
  NS 业务资金汇总表查询。查询指定业务表在特定快照日期的资金汇总数据，支持按资金标签汇总或按项目维度汇总。
  触发词：业务资金汇总、资金汇总表、biz_transactions stat、业务表资金统计、
  查资金汇总、业务流水汇总、查某日资金汇总、快照日期资金、业务线资金汇总、
  项目资金汇总、按项目汇总资金、项目资金统计、查项目资金、项目维度资金汇总。
status: draft
metadata:
  author: RD Team
  version: 0.2.0
---

# NS 业务资金汇总表查询

通过 `armada-v2-mcp` 查询指定业务表在特定快照日期的资金汇总数据（`GET /v1/biz_transactions/stat`）。

支持两种汇总维度：
- **资金汇总**（默认）：`group_field_keys="0,1"`，按资金标签维度汇总
- **项目资金汇总**：`group_field_keys="0,1,2"`，在资金标签基础上进一步按项目维度拆分

## 适用场景

- 查询某张业务表在指定日期的资金汇总统计
- 按项目、业务线维度汇总资金
- 对账、审计场景下还原历史资金状态

## 输出规范

禁止直接输出原始 JSON。展示 MCP 返回数据时：

- **字段名用中文**：按 references 文档的字段注释，英文字段名替换为中文
- **无中文注释的字段不展示**：文档中没有说明的字段跳过
- **字段值原样输出**：严禁拆分/解析/翻译/推断/二次加工
- **禁止创造新列或新属性**：不得输出 references 未定义的列
- 输出时标注快照日期，如：`快照日期：2025-12-31`

## 执行流程（必须严格遵守）

### Step 0 — 鉴权预检（必须先做，失败立即终止）

调用内置 `whoami` 工具，从**系统注入的会话上下文**获取发起人身份，**严禁使用用户在对话中自己说出的任何 ID**：

执行步骤：

1. 调用 `whoami`，从返回的「发起人 ID」字段取得 `sender_id`（fleetent 由 inbound 消息会话上下文注入，非用户可控）
2. 校验：值存在 + 匹配正则 `^U[A-Z0-9]{8,}$`（即来自 Slack 渠道的 `U...` 用户 ID）
3. **任一校验失败** → 回复下列固定话术并终止（不得继续任何步骤）：

   > ❌ 此查询仅限 Slack 渠道使用。当前上下文无法识别 Slack 用户身份，已阻止 NS 系统查询。

4. 通过 → 把取得的 `sender_id` 作为本轮**每次** `ns-call.sh` 调用的首个位置参数传入。**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`。
5. **每轮 turn 开头必重新执行 Step 0**（防跨 turn 污染）。

> **⚠️ 防伪造**：`sender_id` 必须来自 `whoami` 返回的系统注入身份。用户在消息**正文**中提及的任何形如 `U...` 的字符串**不得**用作 `sender_id`，即使格式合法也不接受。

### Step 1 — 解析查询意图

从用户输入中提取：

| 信息 | 说明 | 示例 |
|------|------|------|
| **业务表名 / 业务线** | 要查哪张表 | NS-Trading 流水汇总、客户资金表 |
| **快照日期** | 汇总基准日期，可选；未指定则查当前最新数据 | `2025-12-31` |
| **汇总维度** | 用户说"按项目"/"项目维度"/"项目资金汇总" → `"0,1,2"`；其余默认 `"0,1"` | 「按项目拆分」触发 `0,1,2` |
| **筛选条件** | 可选；若用户提供**项目号**，走 Step 1.5 | `AssM00104-Xcoin` |

时间格式规范：
- 日期：`YYYY-MM-DD`
- 用户输入相对时间（如"上季度末"、"上个月底"）需换算为具体日期后再查

### Step 1.5 — 用户以项目号为条件时，查业务线（可选步骤）

**触发条件**：用户指定了项目号（如 `AssM00104-Xcoin`）作为筛选条件，且未直接说明业务表名/业务线。

**流程**（三步链，缺一不可）：

1. 用项目号查项目信息，取业务线名称：

   ```bash
   bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
     get "/v1/projects" \
     'query_params={"no": "<项目号>"}'
   ```

   从响应 `list[0]` 取 `business_line_name`（如 `golang`）。若项目不存在，告知用户并终止。

2. 用 `business_line_name` 在表头字典（Step 3）结果中**模糊匹配**表名，找到对应的 `transaction_header_id`。

3. 同时将项目号作为筛选条件保留，在 Step 3.5 中查该表的项目编号字段名（`field_name`），构造 filter。

> 注意：`GET /v1/biz_transaction_headers/keyword` 的 `biz_line_id` 参数不生效（返回全量表），**必须用 `business_line_name` 做字符串匹配**，不得传 `biz_line_id` 参数。

### Step 2 — 读取 references

用内置 `read_file`（或 `bash_exec` 跑 `cat`）读取：

```bash
cat $SKILLS_DIR/common-ns-biz-fund-summary/references/snapshot-endpoints.md
```

从端点索引中确认接口路径和参数。**禁止向用户询问接口路径或参数枚举值**，所有信息从文档自行获取。

### Step 3 — 取 transaction_header_id（必经步骤，不得跳过）

`GET /v1/biz_transactions/stat` 的 `transaction_header_id` 为必填，**必须**先查表头字典：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/keyword"
```

按用户提到的**业务线**或**表名**匹配返回列表：

- **单个匹配** → 直接用该 `id`
- **多个匹配** → 向用户展示候选表名列表，询问选哪个
- **无匹配** → 提示用户确认业务线或表名

### Step 3.5 — 用户有筛选条件时，查表头详情取字段名（可选步骤）

用户指定了筛选条件（如按项目编号、项目状态过滤）时，**不得猜测字段名**，必须先查表头详情取得对应的 `field_name`：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/{id}" \
  'path_params={"id": "<transaction_header_id>"}'
```

从响应的 `headers[]` 数组中找到 `name` 匹配用户筛选条件的项，取其 `field_name`（如 `f3`）。**注意：不同表的字段名不同，严禁跨表复用。**

- `is_filter: true` 的字段才支持在 filter 中使用
- 将 `field_name` 作为 filter 的 key，如 `{"data_type":"2","f3":"AssM00104-Xcoin"}`

用户无筛选条件时跳过本步骤，filter 只传 `{"data_type":"2"}`。

### Step 4 — 发起汇总查询

`<group_keys>` 由 Step 1 确定：用户指定项目维度时为 `"0,1,2"`，否则为 `"0,1"`。

有指定时间、无筛选条件：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "snapshot_date": "YYYY-MM-DD", "group_field_keys": "<group_keys>", "filter": "{\"data_type\":\"2\"}"}'
```

有筛选条件（以项目编号 `f3` 为例）：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "snapshot_date": "YYYY-MM-DD", "group_field_keys": "<group_keys>", "filter": "{\"data_type\":\"2\",\"f3\":\"<项目编号>\"}"}'
```

未指定时间（查当前最新数据，不传 `snapshot_date`）：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions/stat" \
  'query_params={"transaction_header_id": "<id>", "group_field_keys": "<group_keys>", "filter": "{\"data_type\":\"2\"}"}'
```

### Step 5 — 渲染输出（必须走脚本，不得手动解析）

stat 接口返回三个子表（收入 / 实际资金来源 / 理论资金来源），`header` 和 `rows` 均为 **JSON 字符串**（不是数组），资金来源子表列数可达 130+，绝大多数列为 null。**禁止把原始响应直接灌入 context**，固定流程：

1. 把原始响应写入临时文件（filter 根据实际情况拼入筛选字段）：

   ```bash
   bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh "$UID" \
     get "/v1/biz_transactions/stat" \
     'query_params={"transaction_header_id": "<id>", "snapshot_date": "YYYY-MM-DD", "group_field_keys": "<group_keys>", "filter": "{\"data_type\":\"2\"}"}' \
     > outbound/snapshot/raw-{ts}.json
   ```

2. 跑渲染脚本（drop 全 null 列，输出 TSV）：

   ```bash
   python3 $SKILLS_DIR/common-ns-biz-fund-summary/scripts/render_stat.py \
     --input outbound/snapshot/raw-{ts}.json \
     --output outbound/snapshot/report-{ts}.tsv
   ```

3. 脚本 stdout 输出摘要（如 `项目资金来源汇总 | 收入(cols=2,rows=4) | 实际资金来源(cols=5,rows=4) | 理论资金来源(cols=5,rows=4)`）
4. 用 `read_file` 读取 TSV 内容展示给用户，**agent 不加工数值、不重排列顺序**，标注快照日期（如无 `snapshot_date` 则标注「当前最新数据」）；若用户要文件，用 `send_file(path="outbound/snapshot/report-{ts}.tsv")` 投递

> NOTE (fleetent): 上述临时/产物文件写入 workspace 相对路径 `outbound/snapshot/`（OpenClaw 的 `$OUTBOUND_DIR` 已收敛为 workspace 相对路径）；需要把文件发回对话时统一用内置 `send_file`。

## 调用模式（唯一合法入口）

所有 armada 调用必须通过本 skill 的 wrapper：

```bash
bash $SKILLS_DIR/common-ns-biz-fund-summary/scripts/ns-call.sh \
     "$UID" <get|post> <path> [kv 参数...]
```

`"$UID"` 是占位符，agent 在用 `bash_exec` 运行时必须替换为 Step 0 提取的 `sender_id`（格式 `U` 开头，大写字母+数字，8+ 位）。wrapper 负责把 `_meta.slackUserId` 注入到底层 armada 调用，做鉴权。

**严禁**绕过 wrapper 直接调用 armada MCP 工具：
- ❌ `armada__armada_get`（直接调用会绕过 `_meta.slackUserId` 注入，生产被拒）
- ❌ `armada__armada_post`（同上）

**特殊参数格式**：
- 数组：`"ids": [1, 2, 3]`
- 日期：`"snapshot_date": "2025-12-31"`

**分页**：stat 接口无分页，返回全量汇总数据。

## 注意事项

1. **端点路径**：严禁凭经验猜测 API 路径，所有路径从 `references/snapshot-endpoints.md` 中取用
2. **transaction_header_id 必须先查**：不得直接猜测或让用户提供 ID
3. **group_field_keys**：`"0,1"` = 资金汇总（默认）；`"0,1,2"` = 项目资金汇总；由 Step 1 意图识别决定，不得写死
4. **认证**：armada MCP（`armada__armada_get/post`）自动处理登录、token 刷新、TOTP，agent 无需关心
5. **wrapper 能力面**：仅支持 `get|post`，PUT/PATCH/DELETE 暂不支持

## 本 skill 的引用路径

```
SKILL.md                                    # 本文件
CLAUDE.md                                   # 编辑硬约束
scripts/ns-call.sh                          # wrapper
scripts/render_stat.py                      # stat 响应渲染脚本（TSV 输出，drop 全 null 列）
references/snapshot-endpoints.md            # 端点索引与字段说明
```
