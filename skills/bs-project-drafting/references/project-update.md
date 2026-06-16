# 更新项目流程

> 所有 `bash_exec: bash ... ns-call.sh ...` 走 **armada 两步交互**（见 SKILL.md）：脚本只打印 `ARMADA_CALL armada__armada_<method> ...` 行，agent 据此发起对应 `armada__armada_<method>` 工具调用拿 JSON，再用 `run_code` 做客户端过滤/匹配/拼装。

## Step 1：定位项目

**提供 project_id（纯数字 15-20 位）**：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/projects/{id}" 'path_params={"id": "<project_id>"}'
```

**提供 project_no（字符串）**：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/projects" 'query_params={"no": "<project_no>", "page_size": "5"}'
```

客户端精确匹配 `list[i].no == project_no`，取命中那条。

- 未找到 → 告知用户"项目不存在"，终止

记录完整响应作为 `current`，提取以下 base 值（PUT 需全量提交）：

| 变量 | 来源 |
|------|------|
| `project_id` | `id` |
| `no` | `no` |
| `status` | `status` |
| `business_line_id` | `business_line_id` |
| `cooperate_company` | `cooperate_company`（原始对象数组，含 id/name/cost_ratio，PUT 时原样回传） |
| `company_id` | `company[*].id`（数组） |
| `start_time` | `start_time` |
| `end_time` | `end_time` |
| `remark` | `remark` |
| `project_desc` | `project_desc` |
| `contains_bm_funds` | `contains_bm_funds`（GET 返回 `0` 时表示未设置，PUT 回传原值即可） |
| `owner_ids` | `owner[*].id`（数组） |

## Step 2：从用户输入提取要更新的字段

| 用户意图 | 字段 | 处理 |
|----------|------|------|
| 改状态（运行/结束/筹备） | `status` | 筹备→1 / 运行→2 / 结束→3 |
| 改备注 | `remark` | 直接取文本 |
| 改开始/结束时间 | `start_time` / `end_time` | UTC `YYYY-MM-DD HH:MM:SS` |
| 改签署主体 | `company_id` | 需查询解析（见下） |
| 改客户/合作方 | `cooperate_company` | 需查询解析（见下） |
| 改业务线 | `business_line` | 需查询解析（见下） |
| 改负责人 | `owners` | 需查询解析（见下） |
| 改项目简称 | `project_desc` | 直接取文本 |
| 改是否含 BM | `contains_bm_funds` | 含→2 / 不含→1 |

> ⚠️ **客户 ≠ 签署主体**：`cooperate_company`（客户/合作方）和 `company_id`（签署主体）是两个完全不同的字段。用户说"改客户"只改 `cooperate_company`，说"改签署主体"只改 `company_id`，不得混用。

**signing_entity 解析**（仅当用户要改签署主体时）：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/companies/search" 'query_params={"name": "<signing_entity>", "page": 1, "page_size": 10}'
```

- 0 条 → 告知用户"签署主体未找到"，终止
- 1 条 → 展示名称/地区/生效状态，等用户确认后采用
- 多条 → 列出编号让用户选择

记录 `company_id = [list[k].id]`（数组格式）。

**cooperate_company 解析**（仅当用户要改客户/合作方时）：

按客户名称查询：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/customers" 'query_params={"name": "<customer_name>", "page_size": "10"}'
```

- 0 条 → 告知用户"客户未找到"，终止
- 1 条 → 展示名称，等用户确认后采用
- 多条 → 列出编号让用户选择

记录 `cooperate_company = [{"id": "<customer_id>", "name": "<customer_name>", "cost_ratio": <原值或null>}]`（PUT 时回传数组格式）。

**business_line 解析**（仅当用户要改业务线时）：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines" 'query_params={"name": "<business_line>", "page_size": "10"}'
```

- 0 条 → 告知用户"业务线未找到"，终止
- 1 条 → 自动采用
- 多条 → 列出编号让用户选择

记录 `business_line_id`。

**owners 解析**（仅当用户要改负责人时）：

对每一项 `o`：纯数字 15-20 位 → 直接使用；含 `@` → 按邮箱查；否则按昵称查。

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  get "/v1/users" 'query_params={"nickname": "<o>", "page_size": "10"}'
```

- 0 条 → 告知用户"负责人未找到"，终止
- 1 条 → 自动采用
- 多条 → 列出编号让用户选择

意图判断：
- "改成/设为/替换" → `owner_ids = resolved`
- "添加/新增/加上" 或意图不明 → `owner_ids = 去重合并(base.owner_ids + resolved)`

## Step 3：确认变更（≥ 3 个字段或涉及 owners 时）

若仅 1-2 个字段且不含 owners，直接执行 Step 4。

否则，展示变更摘要等用户确认：

```
即将更新项目 <project_no>，请确认：

  <字段中文名>：<旧值> → <新值>
  ...

Y 确认 / N 取消
```

时间字段旧值展示时转 UTC+8。

## Step 4：PUT 执行

> ⚠️ PUT body 必须包含全量字段，缺字段会导致 NS 侧字段被清空。

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  put "/v1/projects/{id}" \
  'path_params={"id": "<project_id>"}' \
  'body={
    "no": "<no>",
    "status": <status>,
    "business_line_id": "<business_line_id>",
    "cooperate_company": [{"id": "<customer_id>", "name": "<customer_name>", "cost_ratio": <原值或null>}],
    "company_id": ["<company_id>"],
    "start_time": "<start_time>",
    "end_time": "<end_time>",
    "remark": "<remark>",
    "project_desc": "<project_desc>",
    "contains_bm_funds": <contains_bm_funds>,
    "owner_ids": ["<owner_id...>"]
  }'
```

- HTTP 2xx 且 body 无 `error_code` → 成功
- body 含 `error_code` → 告知用户错误详情，终止

## Step 5：输出结果

```
项目更新成功 ✅

已更新字段：
  <字段中文名>：<旧值> → <新值>
  ...

项目详情：https://admin.nsdigital.io/sensitive/project/collect/detail?id=<project_id>
```

URL 中的 `<project_id>` 使用 Step 1 记录的 `project_id`。
