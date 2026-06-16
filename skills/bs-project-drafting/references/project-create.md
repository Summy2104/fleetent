# 新建项目流程

> 所有 `bash_exec: bash ... ns-call.sh ...` 走 **armada 两步交互**（见 SKILL.md）：脚本只打印 `ARMADA_CALL armada__armada_<method> ...` 行，agent 据此发起对应 `armada__armada_<method>` 工具调用拿 JSON，再用 `run_code` 做客户端过滤/匹配/拼装。`run_code: python3 ...` 是纯本地计算（如时间），无 NS 调用。

## Step 1：从用户输入提取字段

从自然语言中提取以下字段。必填字段缺失时，一次性向用户确认，不分多轮。

| 字段 | 必填 | 说明 |
|------|------|------|
| `customer` | 是 | 客户名称或 snowflake ID（15-20 位纯数字） |
| `business_line` | 是 | 业务线名称 |
| `signing_entity` | 是 | 签署主体名称 |
| `project_nos` | 是 | 项目号列表（一个或多个）；末尾含占位符（xx/??/__/*）则忽略，走自动递增 |
| `count` | 否 | 批量创建数量，默认 1；`project_nos` 有值时忽略 |
| `template_project_no` | 否 | 参照项目号，自动补全 customer/company_id/start_time/end_time |
| `owners` | 否 | 负责人列表，支持姓名/邮箱/snowflake ID |
| `project_purpose` | 否 | 备注（写入 `remark`） |
| `project_desc` | 否 | 项目简称（写入 `project_desc`） |
| `start_time` | 否 | UTC `YYYY-MM-DD HH:MM:SS`；默认当日 HKT 零点 |
| `end_time` | 否 | UTC `YYYY-MM-DD HH:MM:SS`；默认 `2099-12-30 16:00:00` |
| `contains_bm_funds` | 否 | `1`=不含 BM / `2`=含 BM |
| `status` | 否 | `1`=筹备 / `2`=运行 / `3`=结束；默认 `1` |

`contains_bm_funds` 提取：含/有/包含/是/要 + BM资金 → `2`；不含/无/没有 + BM资金 → `1`；未提及 → 不传。

## Step 2：解析 customer → 得到 customer_id / customer_name

**若 customer 是 snowflake ID（纯数字 15-20 位）**：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers/{id}" 'path_params={"id": "<customer>"}'
```

- 404 → 告知用户"客户不存在"，终止
- `status != 3` → 告知用户"客户不可用（status=N）"，终止
- 成功 → `customer_id = customer`，记录 `customer_name`（响应 `name`），`customer_code`（响应 `code`）

**若 customer 是名称**：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers" 'query_params={"name": "<customer>", "page_size": "10"}'
```

- 0 条 → 告知用户"未找到客户"，终止
- 1 条 → 自动采用
- 多条 → 列出编号让用户选择，等用户回复后取对应条目

选定后，若未做过 ID 路径校验，再 `GET /v1/customers/{id}` 校验 `status == 3`，记录 `customer_id` / `customer_name` / `customer_code`。

## Step 3：解析 business_line → 得到 biz_line_id

若提供了 `template_project_no` 且用户未指定 `business_line`，则 `biz_line_id` 来自模板（Step 3a），跳过本步。

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines" 'query_params={"name": "<business_line>", "page_size": "10"}'
```

- 0 条 → 告知用户"业务线未找到"，终止
- 1 条 → 自动采用，记录 `biz_line_id`
- 多条 → 列出编号让用户选择，记录 `biz_line_id`

## Step 3a：读取模板项目（仅当 template_project_no 提供时）

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/projects" 'query_params={"no": "<template_project_no>", "page_size": "5"}'
```

客户端精确匹配 `list[i].no == template_project_no`：
- 0 条 → 告知用户"模板项目不存在"，终止
- 命中 → 从响应提取（用户未指定时才使用）：
  - `customer_id` ← `cooperate_company[0].id`
  - `company_id` ← `company[0].id`（跳过 Step 4 签署主体查询）
  - `biz_line_id` ← `business_line_id`（跳过 Step 3）
  - `start_time` ← `start_time`
  - `end_time` ← `end_time`

用户显式指定的字段优先，模板值只补全缺失字段。

向用户展示从模板补全的字段，等确认后继续。

## Step 4：解析 signing_entity → 得到 company_id

若模板已提供 `company_id`（Step 3a），跳过查询直接使用模板值。

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/companies/search" 'query_params={"name": "<signing_entity>", "page": 1, "page_size": 10}'
```

- 0 条 → 告知用户"签署主体未找到"，终止
- 1 条 → 自动采用，记录 `company_id = [list[0].id]`
- 多条 → 列出编号（含注册地区、生效状态）让用户选择，记录 `company_id = [list[k].id]`

## Step 5：解析 owners → 得到 owner_ids（可选）

若未提供 `owners`，跳过本步，POST body 不传 `owner_ids`。

对每一项 `o`：
- 纯数字 15-20 位 → 直接加入 `owner_ids`
- 含 `@` → `GET /v1/users?email=<o>&page_size=10`
- 否则 → `GET /v1/users?nickname=<o>&page_size=10`

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/users" 'query_params={"nickname": "<o>", "page_size": "10"}'
```

- 0 条 → 告知用户"负责人未找到"，终止
- 1 条 → 自动采用
- 多条 → 列出编号（含邮箱）让用户选择

## Step 6：检查历史项目，生成 project_no

**若 project_nos 已指定**（且无占位符）：直接使用，跳到 Step 7。

**否则，查历史生成递增 no**：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/projects" \
  'query_params={"biz_line": "<biz_line_id>", "cooperate_company_name": "<customer_name>", "page_size": "100"}'
```

客户端再按 `cooperate_company[*].id == customer_id` 精确过滤。

**有历史记录（续建）**：
- 收集所有记录的 `no` 和 `former_project_nos` 中的每个 no
- 取每个 no 末尾连续数字（`(\d+)$`）得到整数，取最大值那条作为模板
- `new_no = 模板 no 末尾数字 +1，保持原位宽`
- 例：历史最大 `RWA00201` → new_no = `RWA00202`

**无历史记录（首次）**：
- 若已提供 `project_nos` / `initial_no` → 直接使用
- 否则 → 询问用户："客户 `<customer_name>` × 业务线 `<business_line>` 首次创建，请提供初始项目号（如 ZCDTY00101）"

若有进行中项目（status 1 或 2）：展示已有项目号，询问是否继续创建，用户拒绝则终止。

**批量（count > 1）**：首个 no 按上述规则生成，后续每个在前一个基础上末尾 +1，保持位宽，严格串行执行。

## Step 7：计算默认时间（若未提供）

```bash
run_code: python3 -c "
from datetime import datetime, timezone, timedelta
now_utc = datetime.now(timezone.utc)
hkt_date = (now_utc + timedelta(hours=8)).date()
start = datetime(hkt_date.year, hkt_date.month, hkt_date.day, tzinfo=timezone.utc) - timedelta(hours=8)
print(start.strftime('%Y-%m-%d %H:%M:%S'))
"
```

- `start_time` 默认：上述命令输出值（当日 HKT 零点对应 UTC）
- `end_time` 默认：`2099-12-30 16:00:00`
- 用户指定 > 模板值 > 默认值

## Step 8：POST 创建项目

> ⚠️ 组装 body 前确认以下变量均已赋值，任意一项为空则停止执行，告知用户补充：`biz_line_id`、`customer_id`、`company_id`、`new_no`、`start_time`、`end_time`

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/projects" \
  'body={
    "business_line_id": "<biz_line_id>",
    "cooperate_company": [{"id": "<customer_id>", "name": "<customer_name>", "cost_ratio": null}],
    "no": "<new_no>",
    "status": <status 默认1>,
    "start_time": "<start_time>",
    "end_time": "<end_time>",
    "remark": "<project_purpose 若有>",
    "project_desc": "<project_desc 若有>",
    "company_id": ["<company_id>"],
    "owner_ids": ["<owner_id...>"],
    "contains_bm_funds": <contains_bm_funds 若有>
  }'
```

- `company_id` 必填，数组格式（来自 Step 4）
- `owner_ids` 仅当 Step 5 已解析时传入（数组格式）
- `contains_bm_funds` 仅当用户提供时传入
- `cooperate_company` 必须是对象数组，包含 `id`、`name`、`cost_ratio: null`

响应：`{ "id": "<ns_project_id>" }` — 记录 `ns_project_id`。

POST 返回 `duplicated key not allowed` → 重新执行 Step 6 取最新 max +1，重试 1 次。

## Step 9：输出结果

```
项目创建成功 ✅

项目号：<new_no>
业务线：<business_line>
客户：<customer_name>
状态：筹备（1）/ 运行（2）/ 结束（3）
开始时间：<start_time UTC+8>
结束时间：<end_time UTC+8>
签署主体：<company_name 或 未提供>
负责人：<owner_names 或 未提供>
是否含 BM 资金：<不含/含/未提供>
项目简称：<project_desc 或 未提供>
备注：<project_purpose 或 未提供>

项目详情：https://admin.nsdigital.io/sensitive/project/collect/detail?id=<ns_project_id>
```

URL 中的 `<ns_project_id>` 必须是 Step 8 POST 响应的 `id` 字段值。

输出后询问用户：

```
是否将项目状态切换为运行中？Y / N
```

- Y → PUT `/v1/projects/{id}` 全量提交，将 `status` 改为 `2`，其余字段保持创建时的值，完成后回复"项目状态已更新为运行中 ✅"
- N / 无回复 → 保持筹备中，不做任何操作

**批量时**，每个项目 POST 完成后记录结果，全部完成后汇总输出，每条成功项目完整展示以下信息：

```
批量创建结果（共 N 个）：

✅ 成功 X 个：

【<project_no_1>】
项目号：<project_no_1>
业务线：<business_line_name>
客户：<customer_name>
签署主体：<company_name>
状态：筹备中（1）/ 运行中（2）
开始时间：<start_time UTC+8>
结束时间：<end_time UTC+8>
负责人：<owner_names 或 未提供>
是否含 BM 资金：<不含/含/未提供>
项目简称：<project_desc 或 未提供>
备注：<remark 或 未提供>
项目详情：https://admin.nsdigital.io/sensitive/project/collect/detail?id=<ns_project_id_1>

【<project_no_2>】
...（同上格式）

⏭️ 跳过（已存在）：<no> ...
❌ 失败：<no>（<原因>）...
```
