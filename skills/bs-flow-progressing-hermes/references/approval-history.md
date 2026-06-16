# 审批历史查询参考

> **⚠️ 鉴权契约**：所有示例中的 `"$UID"` 是占位符，agent 在实际调用时须替换为 Step 0 从 ToolContext 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 `scripts/ns-call.sh` wrapper 自动注入（打印进 `ARMADA_CALL` 行）。严禁绕过 wrapper 直接发起 `armada__armada_get`。

## 接口

`GET /v2/bpmn/process_instance/{mongo_id}/tasks`

```bash
bash_exec: bash $SKILLS_DIR/bs-flow-progressing-hermes/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/tasks" \
  'path_params={"mongo_id": "<mongo_id>"}'
```
（拿 `ARMADA_CALL` 行后发起 `armada__armada_get` 取 JSON）

## 响应字段（`list[]`，按 operate_time 升序）

| 字段 | 类型 | 说明 |
|------|------|------|
| list[].name | string | 节点名称 |
| list[].type | string | 节点类型：`start`=发起，`approval`=审批，`submit`=提交，`payment`=付款 |
| list[].action | string | 操作动作：`pass`=通过，`auto_pass`=自动通过，`submit`=提交，`partial_submit`=部分提交，`batch_submit`=批量提交，`reject`=拒绝；**为空或 null 表示该节点尚未操作** |
| list[].operator_name | string | 操作人 |
| list[].operate_time | string | 操作时间（RFC3339，展示时转 UTC+8） |
| list[].reason | string | 审批意见（可为空） |

## 字段提取规则（用于 Step 4.2 催办消息）

**已完成节点**：`action` 非空（`pass` / `auto_pass` / `submit` / `partial_submit` / `batch_submit` / `reject`）。
**未完成节点**：`action` 为空或 `null`（待审批，尚未操作）。

| 目标字段 | 提取方式 |
|----------|----------|
| `last_actor` | 已完成节点中最后一个的 `operator_name` |
| `last_action` | 已完成节点中最后一个的 `action` 翻译：`pass`→通过，`auto_pass`→自动通过，`submit`→提交，`partial_submit`→部分提交，`batch_submit`→批量提交，`reject`→拒绝 |
| `last_comment_excerpt` | 已完成节点中最后一个的 `reason`，截取前 20 字；为空则整个括号省略 |
| `remaining_chain_brief` | 未完成节点的 `name` 列表，按顺序用 " → " 连接 |
| `n_remaining` | 未完成节点数量 |

**降级**：接口失败时跳过以上所有字段，不阻塞催办消息发送。
