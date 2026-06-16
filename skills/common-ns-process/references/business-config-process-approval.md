# 业务配置 - 流程管理与审批管理 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #3**：查流程 XML / 审批配置先取 mongo_id（非 id），见父 skill `references/common-query-chains.md#链-3`。

## 流程管理 (Process)

### GET /v1/bpmn/category — 流程类别列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" get "/v1/bpmn/category"
```

**请求参数**：无

**响应字段**

| 字段名 | 类型 | 说明 |
|---|---|---|
| categories | array | 流程类别列表 |

---

### GET /v1/bpmn/process_definition/list — 流程定义列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/process_definition/list" \
  'query_params={"process_name": "付款流程", "exclude_draft": true, "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| process_category_id | string | 流程类别 ID |
| process_name | string | 流程名称（模糊匹配） |
| exclude_draft | bool | 是否排除草稿，**默认传 `true`**（草稿记录 `id` 为空，无法查询 XML） |
| exclude_deactivate | bool | 是否排除已停用 |
| page | int | 页码 |
| page_size | int | 每页数量 |

> **查询已发布流程时**，建议加 `exclude_draft=true`，避免取到 `id` 为空的草稿记录。

**响应字段**（`list` 列表项）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 流程定义 ID（草稿状态下可能为空，**不可**用于 XML 端点） |
| mongo_id | string | MongoDB 文档 ID（**必须**用于 XML 端点的 `{id}` 路径参数） |
| key | string | 流程 Key |
| name | string | 流程名称 |
| memo | string | 备注 |
| version | string | 版本号 |
| category_id | string | 所属类别 ID |
| category_name | string | 所属类别名称 |
| enabled | bool | 是否启用 |
| is_draft | bool | 是否为草稿 |
| created_at | string | 创建时间 |
| released_at | string | 发布时间 |

**响应字段**（顶层）

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 流程定义列表 |
| pageInfo | object | 分页信息（驼峰命名） |

---

### GET /v1/bpmn/process_definition/{mongo_id}/xml — 流程图 XML

> **两步查询**：先调用 `/v1/bpmn/process_definition/list`（加 `exclude_draft=true`）取到目标流程的 `mongo_id`，再以 `mongo_id` 作为路径参数调用本接口。**不可使用 `id` 字段**（草稿下为空，非草稿下格式不同）。

```bash
# Step 1：取 mongo_id（默认排除草稿）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/process_definition/list" \
  'query_params={"process_name": "AA补保", "exclude_draft": true, "page": 1, "page_size": 20}'

# Step 2：用 mongo_id 查 XML
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/process_definition/{mongo_id}/xml" \
  'path_params={"mongo_id": "<mongo_id from step 1>"}'
```

**Path 参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| mongo_id | string | 流程的 `mongo_id`（来自列表接口） |

**响应字段**

| 字段名 | 类型 | 说明 |
|---|---|---|
| xml | string | 流程图 XML 内容 |
| task_form_variables | object | 表单变量定义 |

---

## 审批管理 (Approval)

### GET /v1/bpmn/approver/phrases — 审批短语列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/approver/phrases" \
  'query_params={"keyword": "同意", "recent_only": true}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| keyword | string | 搜索关键词 |
| recent_only | bool | 是否只返回最近 10 条，默认 `false`；当 `keyword` 为空时建议设为 `true` |

**响应字段**

| 字段名 | 类型 | 说明 |
|---|---|---|
| phrases | array | 审批短语列表（注意：顶层字段为 `phrases`，非 `list`） |

---

### GET /v1/management/approver/group/list — 审批组列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/management/approver/group/list" \
  'query_params={"name": "财务审批组", "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| name | string | 审批组名称（模糊匹配） |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**（`list` 列表项）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 审批组 ID |
| name | string | 审批组名称 |
| description | string | 描述 |
| enabled | bool | 是否启用 |
| email_group | array[string] | 邮件组 |
| leader_group_id | string | 上级审批组 ID |
| leader_group_name | string | 上级审批组名称 |
| updated_at | string | 更新时间 |

**响应字段**（顶层）

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 审批组列表 |
| pageInfo | object | 分页信息（驼峰命名） |

---

### GET /v1/management/approver/list — 审批人列表

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/management/approver/list" \
  'query_params={"approver_group_id": "group-123", "user_email": "user@example.com", "page": 1, "page_size": 20}'
```

**请求参数**

| 参数名 | 类型 | 说明 |
|---|---|---|
| approver_group_id | string | 审批组 ID |
| biz_line_id | string | 业务线 ID |
| user_name | string | 用户名称（模糊匹配） |
| user_email | string | 用户邮箱（模糊匹配） |
| page | int | 页码 |
| page_size | int | 每页数量 |

**响应字段**（`list` 列表项）

| 字段名 | 类型 | 说明 |
|---|---|---|
| id | string | 审批人 ID |
| user_id | string | 用户 ID |
| user_name | string | 用户名称 |
| user_email | string | 用户邮箱 |
| enabled | bool | 是否启用 |
| is_all_biz_lines | bool | 是否覆盖全部业务线 |
| approver_groups | array | 所属审批组列表，每项包含 `id`、`name` |
| biz_lines | array | 关联业务线列表，每项包含 `id`、`name` |
| created_at | string | 创建时间 |

**响应字段**（顶层）

| 字段名 | 类型 | 说明 |
|---|---|---|
| list | array | 审批人列表 |
| pageInfo | object | 分页信息（驼峰命名） |
