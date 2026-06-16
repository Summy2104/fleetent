# 流程看板查询参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #4**：按审批人筛选流程时，先到父 skill `references/common-query-chains.md#链-4` 取 approver_id。业务线筛选字段名 `biz_line_id` 见 `references/common-id-mapping.md#业务线字段名陷阱`。

用于查询流程列表：判断流程是否存在、按多条件筛选流程、展示流程审批状态及进度。

> 如需查询**资金流水明细**（含金额、币种、出入账等），请参考 `references/transactions-logical.md`。

---

## 流程看板查询

支持按流程状态、流程编号、流程定义名称、项目号、发起人、邮件标题、审批人、时间范围等多条件筛选，返回流程简略信息。适合判断流程是否存在、或输出多条流程供用户选择。

---

### 接口：`GET /v1/bpmn/dashboard/all`

**请求参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| process_state | string | 流程状态：`running`=审批中，`completed`=已完成，`manual_completed`=手动已完成（`completed` 的子集，已包含在 `completed` 查询结果中），`canceled`=已撤销，`abandoned_approval`=作废审批中，`abandoned`=已作废，`archived`=已归档 |
| process_no | string | 流程编号（模糊匹配） |
| process_definition_name | string | 流程定义名称（模糊匹配） |
| biz_line_id | string | 业务线 ID |
| category_id | string | 流程类别 ID：`1960972591436304395`=合同类别，`1953024657617154048`=资金申请，`1798977620446650368`=通用，`1960972591436304384`=轧差 |
| project_number | string | 项目号（模糊匹配） |
| starter | string | 发起人用户名（模糊匹配，如 `xin.cheng`）。**直接传给 API 做服务端筛选，`pageInfo.total` 即为真实总数，禁止在返回结果中做客户端二次过滤或手动统计** |
| email_subject | string | 邮件主题关键词（模糊匹配） |
| process_instance_mark | string | 流程标记（模糊匹配） |
| approver_id | string | 审批人 ID（先通过 `GET /v1/management/approver/list` 按 `user_name` 或 `user_email` 匹配获取 `id`，再传入此参数） |
| submit_start_time | string | 提交开始时间，格式 `2026-03-31 06:31:56` |
| submit_end_time | string | 提交结束时间，格式 `2026-04-01 06:31:54` |
| finish_start_time | string | 完成开始时间，格式 `2026-04-09 06:32:01` |
| finish_end_time | string | 完成结束时间，格式 `2026-04-24 06:32:04` |
| page | int | 页码，从 1 开始 |
| page_size | int | 每页数量，建议 20 |

**响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| list[].process_no | string | 流程编号（11位，如 `20260409008`） |
| list[].process_instance_id | string | 流程实例 ID |
| list[].email_subject | string | 邮件标题 |
| list[].process_state | string | 流程状态：`running`=审批中，`completed`=已完成，`manual_completed`=手动已完成（`completed` 的子集，已包含在 `completed` 查询结果中），`canceled`=已撤销，`abandoned_approval`=作废审批中，`abandoned`=已作废，`archived`=已归档 |
| list[].process_definition_name | string | 流程定义名称 |
| list[].task_name | string | 当前审批节点名称 |
| list[].current_assignee | string | 当前待审批人（逗号分隔） |
| list[].starter_name | string | 发起人 |
| list[].project_number_list | string | 关联项目号 |
| list[].business_line_list | string | 关联业务线（逗号分隔） |
| list[].created_at | string | 创建时间（UTC，展示转 UTC+8） |
| pageInfo.total | string | 总条数 |

**展示规范**

以表格展示，列顺序：# | 流程编号 | 邮件标题 | 流程定义 | 当前节点 | 状态 | 发起人 | 创建时间

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/bpmn/dashboard/all" \
  'query_params={"email_subject": "【项目调仓】Defi0030901", "page": 1, "page_size": 20}'
```

---

## 流程进度查询（用户问"进度"或"审批到哪里了"时执行）

对第一步返回的 `process_instance_id`，调用流程实例详情接口。

`GET /v2/bpmn/process_instance/{mongo_id}`

**关键响应字段**

| 字段 | 类型 | 说明 |
|------|------|------|
| status | string | `running`=审批中，`completed`=已完成，`canceled`=已撤销 |
| active_camunda_task_id | string | 当前活动任务 ID（非空时表示有待审批节点） |
| basic_info.process_number | string | 流程编号 |
| basic_info.process_definition.name | string | 流程定义名称 |
| basic_info.custom_email_title | string | 流程标题 |
| basic_info.starter_name | string | 发起人 |
| basic_info.created_at | string | 创建时间（UTC，展示转 UTC+8） |

若 `active_camunda_task_id` 非空，继续查当前审批节点：

`GET /v2/bpmn/process_instance/{mongo_id}/task/{task_id}`

| 字段 | 类型 | 说明 |
|------|------|------|
| form.name | string | 当前审批节点名称 |
| form.assignees[].name | string | 当前审批人 |

**展示规范**

在流程列表后，对每条 `status=running` 的流程追加进度信息：

```
**进度：审批中**
当前审批节点：{form.name}
当前审批人：{assignees[].name 顿号连接}
```

已完成/已撤销的流程只展示状态，不查任务详情。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}" \
  'path_params={"mongo_id": "69d4f4008e012fe1641820a9"}'
```
