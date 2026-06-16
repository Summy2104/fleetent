# 跨域 ID→名称映射 字典接口集

> **⚠️ 鉴权契约**：本文档所有示例中的 `"$UID"` 是占位符，agent 在实际用 bash_exec/run_code 运行 wrapper 时须替换为 Step 0 从 incoming JSON 提取的 `sender_id`。`_meta={"slackUserId":"..."}` 由 wrapper 内部自动注入。**严禁绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post` 工具**。规则见 `SKILL.md §调用模式`。

当你需要把 ID 翻译成名字、或需要按名字反查 ID 时，**一律使用本文档的字典接口**，**不要**去查对应详情接口。这些接口返回**全量**数据（不分页、不过滤），适合在 skill 中缓存后复用。

## 1. 字典接口清单（11 个）

| # | 接口 | 用途 | 字段名陷阱 |
|---|------|------|-----------|
| 1 | `GET /v1/biz_lines/keyword` | 业务线 ID ↔ 名称 | ⚠️ 业务线 **ID 字段名多变**：项目接口用 `biz_line`（单数、ID）；客户接口用 `biz_line_ids`（复数、数组）；流程接口用 `biz_line_id`（单数、下划线 id）——调用方需看具体端点文档 |
| 2 | `GET /v1/customers/keyword` | 客户 ID ↔ 名称 | — |
| 3 | `GET /v1/companies/keyword` | 主体（公司）ID ↔ 名称 | ⚠️ 不要与 `customer` 混淆：`company` 是我方主体，`customer` 是对方客户 |
| 4 | `GET /v1/users/keyword` | 用户 ID ↔ 名称（姓名/邮箱）| — |
| 5 | `GET /v1/projects/labels` | 项目 ID ↔ 名称 | ⚠️ 接口是 `/labels` 不是 `/keyword` |
| 6 | `GET /v1/department/keyword` | 部门 ID ↔ 名称 | ⚠️ 是 `department`（单数），不是 `departments` |
| 7 | `GET /v1/behavior/label` | 行为 ID ↔ 名称 | ⚠️ 是 `/label` 不是 `/keyword` |
| 8 | `GET /v1/accounts/bank/label` | 银行 ID ↔ 名称 | ⚠️ 是 `/label` |
| 9 | `GET /v1/accounts/platform/label` | 平台 ID ↔ 名称（数币账户平台）| ⚠️ 是 `/label` |
| 10 | `GET /v1/coins/mo` + `GET /v1/coins/nets` | 数币 ID ↔ 符号 / 链 ID ↔ 链名 | 两个独立接口：`mo` 是币种，`nets` 是链 |

## 2. 业务线的特殊地位

业务线 `biz_line` 是**全仓根依赖**：

- 22 份 references 里有 13 份需要它（客户/项目/合同/流程/流水筛选/审批配置等）
- **强制缓存建议**：任何子 skill 触发时若未缓存过业务线字典，**第一次调用前**先拉一次：

  ```bash
  bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
    get "/v1/biz_lines/keyword"
  ```

- 缓存建议保留本轮 turn 内复用；跨 turn 不保证（每轮可能换 sender）

## 3. keyword 与详情接口的区别

| 场景 | 用 keyword/label 字典 | 用详情接口 |
|------|---------------------|-----------|
| 只要知道 ID 对应的名字 | ✅ | ❌（浪费） |
| 按名字反查 ID | ✅ | ❌（多数详情接口不支持按名搜索）|
| 需要业务线的 email_group / status / region 等字段 | ❌（字典只返 id+name）| ✅ |
| 需要分页列表 | ❌（字典全量，无分页）| ✅ |
| 做报表渲染时把多个 ID 一次性翻译成名字 | ✅（拉一次全量再本地 map）| ❌（多次详情调用极慢）|

## 4. 字段名的跨端点陷阱

**同一个"业务线"概念，在不同端点的参数字段名不一致**：

| 端点 | 字段名 | 类型 | 备注 |
|------|--------|------|------|
| `GET /v1/projects` | `biz_line` | 单数字符串（ID） | ⚠️ **非** `biz_line_id` |
| `GET /v1/customers` | `biz_line_ids` | **数组** | ⚠️ 支持多业务线筛选 |
| `GET /v1/bpmn/dashboard/all` | `biz_line_id` | 单数字符串（ID） | — |
| `POST /v1/accounts/digital_coin` | （在 body 里）按接口文档 | — | — |
| `GET /v1/contract/list` | `biz_line_id` | 单数字符串 | — |

**结论**：每次构造请求前必须读对应 reference 的参数表，不要假设字段名。

## 5. 调用示例

```bash
# 查业务线字典
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_lines/keyword"

# 查客户字典
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers/keyword"

# 查项目字典（注意是 labels 不是 keyword）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/projects/labels"

# 查数币 + 链字典（两次调用）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/mo"
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/coins/nets"
```

响应格式（以业务线为例）：

```jsonc
{
  "code": 0,
  "data": {
    "list": [
      { "id": "12", "name": "NS-Trading" },
      { "id": "15", "name": "配资" },
      // ...
    ]
  }
}
```

agent 使用时做内存 map：`{ "12": "NS-Trading", "15": "配资", ... }`，后续展示时按 ID 查名字。
