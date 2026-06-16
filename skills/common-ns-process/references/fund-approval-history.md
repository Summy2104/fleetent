# 审批历史 / 流程记录 参考文档

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

> **🔗 查询链 #1**：本文档由 fund.md 按触发条件路由加载；入口流程见父 skill `references/common-query-chains.md#链-1`。

> **前置假设**：本文档由 `fund.md` 按触发条件路由后加载。调用方已持有 `instance_id`。

> **硬性约束（反幻觉）**：展示任何节点前**必须**当次现场调用 `GET /v2/bpmn/process_instance/{mongo_id}/tasks` 拿到**本次流程的真实响应**，再按下方字段映射逐个渲染。严禁：
> - 凭对话上文/会话记忆/其它流程的数据编造节点、TXID、时间；
> - 复用同一会话里之前查过的另一条流程的审批历史；
> - 接口失败或被截断时用占位/估算值代替（截断时用 jq 抽取关键字段分批读）。
> 每个 TXID 必须与 tasks 响应里的 `transaction_hash` 原样一致；时间必须基于本次响应的 `operate_time` 换算 UTC+8。自检：输出后挑一个节点把其 TXID 在原始响应里 grep 一次能搜到，否则作废重做。

## 触发条件

**路径 1（默认询问）**：`fund.md` 前三步 + 资金数据全部输出完毕后，追问一句：

> 以上是流程完整详情。需要查看审批历史记录吗？

- 用户明确同意（是/要/看一下 等）→ 调用本接口展示
- 用户拒绝/跳过/未回答 → 不调用，结束

**路径 2（直接触发）**：用户在初始请求中**直接**说"审批历史"或"流程记录"（或等价说法：审批记录、流程审批记录），跳过 `fund.md` 第一~四步的完整流程和询问环节，直接调用本接口输出审批历史。

**不要混淆**：用户说"走到哪了/走到哪个节点/当前审批节点"查的是**当前**节点，走 `fund.md` 第三步 `/task/{task_id}`，**不要**调用 `/tasks`。

## 接口

`GET /v2/bpmn/process_instance/{mongo_id}/tasks`

**Path 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| mongo_id | string | 流程实例 ID (mongo_id) |

**响应字段（`list[]`，按 operate_time 升序即审批流转顺序）**

| 字段 | 类型 | 说明 |
|------|------|------|
| list[].name | string | 节点名称 |
| list[].description | string | 节点描述（通常与 name 相同） |
| list[].type | string | 节点类型：`start`=发起，`approval`=审批，`submit`=提交资金路径，`payment`=账户管理员付款 |
| list[].action | string | 操作动作：`pass`=通过，`auto_pass`=自动通过，`submit`=提交，`partial_submit`=部分提交，`batch_submit`=批量提交，`reject`=拒绝 |
| list[].operator_name | string | 操作人 |
| list[].operate_time | string | 操作时间 (RFC3339，展示时转为 UTC+8) |
| list[].reason | string | 审批意见 |
| list[].memo | string | 备注（`auto_pass` 会写明原因） |
| list[].signature_result | int | 验签状态：1=已验签，0=未验签 |
| list[].transaction_hash | string | 验签 TXID（区块链哈希，节点有验签时非空） |
| list[].submit_count | int | 同一路径的提交次数（仅 `type=payment` 有意义） |
| list[].fund_path_desc | string | 资金路径描述（如"数币1"） |
| list[].fund_path | object | 资金路径明细（仅 `type=payment` 非 null，见下方展开结构） |

**fund_path 展开结构**（仅 `type=payment` 出现）

| 字段 | 类型 | 说明 |
|------|------|------|
| fund_path.fund_path | array | 支付子路径列表（每个 from 对应一个子账户） |
| fund_path.fund_path[i].currency | string | 子路径计划币种（预估，可能与实际支付币种不同） |
| fund_path.fund_path[i].estimated_amount | string | 该子路径预估金额 |
| fund_path.fund_path[i].from.name | string | 付款方（法人名） |
| fund_path.fund_path[i].from.account.master_account_name | string | 付款主账户 |
| fund_path.fund_path[i].from.account.sub_account_name | string | 付款子账户（存在时表示付款账户为"子账户集"） |
| fund_path.fund_path[i].to.name | string | 收款方（法人名） |
| fund_path.fund_path[i].to.account.master_account_name | string | 收款主账户 |
| fund_path.fund_path[i].to.account.sub_account_name | string | 收款子账户 |
| fund_path.fund_path[i].receipt[].amount | string | 实际支付数量 |
| fund_path.fund_path[i].receipt[].currency | string | **实际支付币种**（与子路径 currency 可能不一致，展示以此为准） |
| fund_path.fund_path[i].receipt[].fee | string | 手续费数量（仅非空时展示） |
| fund_path.fund_path[i].receipt[].fee_currency | string | 手续费币种（仅非空时展示） |
| fund_path.fund_path[i].receipt[].transfer_time | string | 出/入账时间（UTC，展示转 UTC+8） |
| fund_path.fund_path[i].receipt[].tx_id | string | 链上 TXID（为空则展示 -） |

## 展示规范

以标题 `**审批历史**` 起头。**每个节点以独立区块展示**（不用汇总表格），按 operate_time 升序编号 ①②③…

**节点过滤**：只保留 `action ∈ {submit, partial_submit, batch_submit}` 的节点，其余节点（含发起、审批通过/拒绝、付款等）全部从响应 `list[]` 中剔除，再按 operate_time 升序编号。

**通用字段（所有节点）**：

```
{序号} {节点名}：{操作人}  [验签标签]
验签TXID：{transaction_hash 完整输出，不截断}
[{操作动作中文}]
{操作时间 UTC+8}
```

字段映射：
- 节点名 → `name`
- 操作人 → `operator_name`
- 验签标签 → `signature_result == 1` 时展示"已验签"，否则省略整行验签标签与 TXID
- 操作动作中文 → action 枚举翻译：`pass`=通过，`auto_pass`=自动通过（备注通常会说明原因），`submit`=提交，`partial_submit`=部分提交，`batch_submit`=批量提交，`reject`=拒绝
- 操作时间 → `operate_time` 转 UTC+8，格式 `YYYY-MM-DD HH:MM:SS`。**输出时时间值必须用反引号包裹**（如 `` `2026-04-09 16:21:15` ``），否则 Slack 会把 `:21:` 这种片段误识别为 emoji 短代码渲染成表情。同样规则适用于所有出现时间的字段（receipt.transfer_time 等）
- 审批意见 → `reason`，为空则该行省略
- 备注 → `memo`，为空则该行省略

**`type=payment` 节点额外展开 fund_path**：

节点头部加一行：`{fund_path_desc} 第{submit_count}次提交此路径`

随后以两列块展示付款/收款：
```
付款方：{from.name}                    收款方：{to.name}
付款账户：{付款账户展示}                 收款账户：{to.account.master_account_name}
```

付款账户展示规则：
- 若任一子路径的 `from.account.sub_account_name` 非空 → 付款账户展示为"子账户集"
- 否则展示 `from.account.master_account_name`

随后按 `fund_path.fund_path[i]` 展开子账户明细表：

| 子账户 | 支付数量（实际） | 币种（实际支付） | 手续费数量 | 手续费币种 | 出/入账时间 | TXID |
|--------|------------------|------------------|------------|------------|-------------|------|
| sub_account_name | receipt[0].amount | receipt[0].currency | receipt[0].fee | receipt[0].fee_currency | receipt[0].transfer_time (UTC+8) | receipt[0].tx_id |

字段规则：
- **子账户**：整张表所有行的 `sub_account_name` 全为空时，**整列不展示**（从表头删掉）；任一行非空则保留整列，单行空格展示 `-`
- **币种（实际支付）**：取 `receipt[0].currency`，为空 fallback 到 `fund_path[i].currency`，仍为空展示 `-`
- **手续费数量 / 手续费币种**：同级列，与支付数量并排。当**整张表所有行**的 `receipt[0].fee` 和 `receipt[0].fee_currency` 全为空时，**整两列不展示**（从表头删掉）；只要任一行非空，整两列保留，单行为空的单元格展示 `-`
- **TXID**：空则 `-`

**通用列过滤规则**：任何列若整张表所有行都为空（null / 空串），整列从表头删掉；只要有一行非空就保留整列。此规则适用于所有可为空的列（不仅限于上面列出的字段）。

**可附加展示字段**：`payment_deadline`（支付截止日，空则 -）、`资金标签`（若有）、路径状态标记（如"更新"）。

**仍忽略的字段**（结构性元数据，对用户无意义）：attachments、prev_transaction_hash、signature_id、task_id、id、instance_id、assignees、can_handle、dynamic_approver_group、netting_instance_id、process_transaction_id、project_no、required_payment_system、intermediary_bank、counterparty_platform、position、crypto_address（除非用户明确问地址）、fiat_address、bank（除非银行路径）、fund_info_id、hash、transfer_type。

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v2/bpmn/process_instance/{mongo_id}/tasks" \
  'path_params={"mongo_id": "<mongo_id>"}'
```
