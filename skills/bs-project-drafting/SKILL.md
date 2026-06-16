---
name: bs-project-drafting
description: >
  NS 项目草稿管理：新建项目或更新项目字段。
  触发词：NS 项目草稿、项目号生成、立项、批量立项、project drafting、更新项目、修改项目字段、参照项目、查看附加信息、编辑附加信息、项目附加信息
status: active
metadata:
  author: RD Team
  version: 4.0.0
complexity: L2
---

# NS 项目管理（Project Drafting & Updating）

所有 NS API 调用走 **armada 两步交互**：
1. `bash_exec` 跑 `bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" <method> <path> [kv...]`，拿到一行 `ARMADA_CALL armada__armada_<method> path=... <kv...> _meta={...}`（wrapper 只做 uid 校验 + 构造参数，不直接访问 NS）。
2. agent 据此发起对应的 `armada__armada_<method>`（`armada__armada_get` / `armada__armada_post` / `armada__armada_put` / `armada__armada_delete`）工具调用，参数即 ARMADA_CALL 行里的 `path=` + 各 kv + `_meta`，拿到 NS 返回的 JSON。
3. 如需对 JSON 做过滤/合并/裁剪/格式化，用 `run_code`（python）加工，不要假设沙箱内能直接拿到 armada JSON。

`$UID` 来源：fleetent ToolContext 的 `slackUserId`（发起对话的用户）。

## 模式判断

- 用户提供了 `project_id` 或 `project_no` → **更新模式**，读 `references/project-update.md`
- 否则 → **新建模式**，读 `references/project-create.md`

> 执行前必须先读对应 reference 文件，不得凭记忆执行。

## 新建模式概览

从用户输入提取字段 → 解析客户 → 解析业务线 → 解析签署主体（可选）→ 解析负责人（可选）→ 生成项目号 → 计算默认时间 → POST 创建 → 输出结果。

**必填字段**：`customer`（客户名称或 snowflake ID）、`business_line`（业务线名称）、`signing_entity`（签署主体）、项目号（可手动指定或自动递增，POST 前必须已确定）。

**可选字段**：`project_nos`（手动指定项目号）、`count`（批量数量，默认 1）、`template_project_no`（参照项目）、`signing_entity`、`owners`、`project_purpose`（备注）、`project_desc`（项目简称）、`start_time`、`end_time`、`contains_bm_funds`。

创建完成后默认状态为筹备中（status=1），输出结果后询问用户是否切换为运行中，确认则 PUT 更新 status=2。

项目号生成规则：
- `project_nos` 指定（无占位符）→ 直接使用
- 有历史记录 → 取历史 no 末尾最大数字 +1，保持原位宽（续建）
- 无历史记录 → 询问用户提供初始项目号

## 更新模式概览

定位项目（GET 取全量字段作为 base）→ 提取用户要改的字段 → 解析需查询的字段（signing_entity/business_line/owners）→ 确认变更（≥3 字段或含 owners 时）→ PUT 全量提交 → 输出结果。

> ⚠️ PUT 必须提交全量字段，缺字段会导致 NS 侧数据被清空。

## 通用规则

**模糊匹配**：查询返回 0 条 → 告知用户并终止；1 条 → 自动采用；多条 → 列出编号让用户选择。

**错误处理**：GET/PUT/POST 超时重试 1 次，仍失败告知用户。

**输出链接格式**：`https://admin.nsdigital.io/sensitive/project/collect/detail?id=<ns_project_id>`，`ns_project_id` 来自 POST 响应的 `id` 字段或 GET 响应的 `id` 字段。

**扩展详情附加**（两步交互）：定位到项目（拿到 `project_id` 和 `business_line_name`）后：

1. `bash_exec` 跑 resolve 模式，解析 `ext_type` 并拿到 GET 扩展详情的 ARMADA_CALL 行：

   ```bash
   bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/fetch-project-extensions.sh \
     "$UID" "<project_id>" "<business_line_name>"
   ```

   - 输出 `（无对应扩展详情）` → 直接跳过，不附加扩展信息。
   - 否则输出三行：`EXT_TYPE=...`、`EXT_NAME=...`、`ARMADA_CALL armada__armada_get path=/v1/projects/{id}/extensions/<ext_type> path_params={"id":"..."} _meta={...}`。

2. agent 据 ARMADA_CALL 行发起 `armada__armada_get` 拿到扩展详情 JSON。查询失败（如 4xx）→ 提示「（扩展详情查询失败：…）」，不阻断主流程。

3. 用 `run_code`（python）把 JSON 按中文字段名格式化，或 `bash_exec` 跑 format 模式（把 armada JSON 喂回脚本）：

   ```bash
   bash_exec: echo '<armada JSON>' | bash $SKILLS_DIR/bs-project-drafting/scripts/fetch-project-extensions.sh --format "<EXT_NAME>"
   ```

   把结果拼接到项目信息后面。

**扩展类型解析**：无论是查询还是写入扩展详情，都必须先读 `scripts/fetch-project-extensions.sh` 中的 `resolve_extension()` 函数，根据 `business_line_name` 确认对应的 `ext_type`（如 `internal_pledge_loans`、`external_pledge_loans` 等），不得凭记忆猜测路径。

**扩展详情字段说明**：扩展详情的 API 字段与中文含义对照如下（展示给用户时使用中文名）：

| API 字段 | 中文名 |
|----------|--------|
| `annual_interest_rate` | 年化利率 |
| `collateral_account` | 质押金所在账户 |
| `collateral_platform` | 质押金所在平台 |
| `initial_ltv` | 初始LTV |
| `liquidation_ltv` | 强平LTV |
| `supplementary_ltv` | 补保LTV |
| `supplementary_time_limit` | 补保时限 |
| `maturity_date` | 到期日 |
| `value_date` | 起息日 |
| `period` | 周期 |
| `settlement_method` | 结算方式 |
| `prime_order_no` | Prime订单号 |
| `prime_fee_rate` | Prime手续费率 |
| `channel_party` | 渠道方 |
| `related_project_no` | 关联项目号 |
| `withdrawal_limit` | 可提保上限 |
| `type` | 类型 |
| `preferred_sharing_ratio` | 优先分润比例 |
| `secondary_sharing_ratio` | 劣后分润比例 |
| `strategy_description` | 策略说明 |
| `strategy_type` | 策略类型 |
| `settlement_period` | 结算周期 |
| `observer_link` | 观察者链接 |
| `mining_pool` | 质押金所属矿池 |
| `mining_pool_subaccount` | 矿池子账户 |
| `venue` | 对应场地 |
| `miner_model` | 矿机型号 |
| `miner_number` | 矿机数量 |
| `theoretical_miner_number` | 理论矿机数量 |
| `mining_income_coin` | 挖矿收益币种 |

**扩展详情写入**：POST 路径为 `/v1/projects/extensions/{type}`（不含 `{id}`），`project_id` 放 body，`id` 为空字符串（新建）或已有扩展记录的 id（更新）。先 `bash_exec` 跑 ns-call.sh 拿 ARMADA_CALL 行，再发起 `armada__armada_post`：

```bash
bash_exec: bash $SKILLS_DIR/bs-project-drafting/scripts/ns-call.sh "$UID" \
  post "/v1/projects/extensions/<ext_type>" \
  'body={"id": "<ext_id_or_empty>", "project_id": "<project_id>", ...}'
```
