---
name: bs-exchange-rate
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台 CEX 母账户费率管理列表查询（middle-mcp `cex_list_exchange_rate_accounts`）。
  注意：本 skill 依赖中台 middle-mcp，fleetent/my-bot 当前 9 个 MCP 面无对应（见正文 NOTE）。
  覆盖 Binance / OKX / Bitget / Gate / Bybit / Deribit 6 家交易所母账户，
  返回账户编码 / 平台 / USD 总估值 / VIP 等级 / 启用状态等字段，支持按平台、
  开户主体、账户编码/名称、状态等过滤，默认按 `-value` 降序前 50 条。
  仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: BS Team
  version: 1.0.0
complexity: L1
---

# CEX 母账户费率管理列表（Exchange Rate Accounts）

> NOTE (fleetent): 此处依赖中台 middle-mcp（`cex_list_exchange_rate_accounts` 工具），my-bot 当前 9 个 MCP 面无对应。
> 已保留原逻辑描述（参数解析 / market 映射 / 字段渲染 / 错误处理）；接入 middle-mcp（注册为 fleetent MCP server，工具名将变为 `{server_id}__cex_list_exchange_rate_accounts`）后即可启用。
> 当前请告知用户：CEX 母账户费率查询需要中台 middle-mcp，本部署暂未接入，请联系对应中台 agent 或运维。

> ⛔ **执行前强制约束**
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 MCP server 的 env 注入，skill 不碰 token。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **数值精度零加工**：`value`（USD 估值）原字面输出，不做 `round()` / `float()` / 千分位转换。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "拉一下 CEX 账户费率列表"
  - "查 alpha 名下在 Binance 的母账户"
  - "看下账户费率管理列表，按估值降序"
- **被其它 skill 调用**：监控/对账类 skill 需要拿一份当前各 CEX 母账户的估值快照与 VIP 等级。

## 能力边界（重要）

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 列出 CEX 母账户（一行一账户） + USD 总估值 + VIP 等级 | ✅ | — |
| 单账户的交易费率明细（按 symbol / VIP 等级） | ❌ | `cex_get_account_trade_fee`（待新建 spoke） |
| 单账户的提币额度 / 链路 / 手续费 | ❌ | `cex_get_account_withdraw_limit`（待新建 spoke） |
| 单账户的借贷信息 / 在借订单 | ❌ | `cex_get_account_borrow_info`（待新建 spoke） |
| 法币历史汇率（如 SGD→HKD 月报） | ❌ | `exchange_rate_get_exchange_rate_report`（待新建 spoke） |
| 账户当前持仓 / 可用 / 冻结 | ❌ | `common-middle-account-assets` |
| 账户某段时间动账明细 | ❌ | `bs-transaction-history` |

## 调用模式

> NOTE (fleetent): 原 OpenClaw/Hermes 经 hub wrapper `middle-call.sh` + `mcpfast` 调中台。fleetent 里 MCP 调用由 agent loop 直接发起（工具名 `{server_id}__<tool>` 双下划线），鉴权由 MCP server 的 env 注入。下文示例的 `middle__cex_list_exchange_rate_accounts` 是占位工具名——middle-mcp 接入并注册为 fleetent MCP server 后，`middle__` 即对应其 server_id。**当前 my-bot 未接入 middle-mcp，本调用无法执行**，请按本文件顶部 NOTE 告知用户。

中台接入后，由 agent loop 直接发起 MCP 工具调用（参数即下方 JSON）：

```text
# 1) 默认查询（前 50 条，按 USD 估值降序）
tool: middle__cex_list_exchange_rate_accounts
args: {"page_num": 1, "page_size": 50, "ordering": "-value"}

# 2) 按平台过滤（market 是 str 多值逗号串，JSON 字符串保留类型）
tool: middle__cex_list_exchange_rate_accounts
args: {"market": "4,10", "page_num": 1, "page_size": 50, "ordering": "-value"}

# 3) 按账户名模糊 + 开户主体名过滤
tool: middle__cex_list_exchange_rate_accounts
args: {"name": "alpha", "account_owner": "alpha", "page_num": 1, "page_size": 50}
```

server resolution / 错误码归类全部由 MCP server 层处理，本 skill 不持有 server 字面 token 知识。

## Market ID 映射

`cex_list_exchange_rate_accounts.market` 是数字 ID（多值用英文逗号）。**当前中台 middle-mcp 没有暴露 `list_market` 字典工具**，市场名 → ID 用下表硬编码（取自工具 docstring，2026-05-29）：

| 市场名 | market_id | 备注 |
|--------|-----------|------|
| Binance | `4` | |
| OKX | `10` | |
| Bybit | `19` | |
| Bitget | `42` | |
| Gate | `43` | |
| Deribit | `44` | VIP 等级 API 不可读，返回值是中台反推估算 |

> 用户给的市场名命中表中条目 → 替换为对应 `market_id`。命中失败 → 不传 `market`，退化为全平台查询，并在输出尾部 `ℹ️` 标注「市场名 `<X>` 未识别，已忽略过滤」。

## 输入参数

所有字段均为可选；用户不提供时使用默认值，**不追问**直接执行。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `id` | int | — | 账户主键 ID 精确匹配 |
| `code` | string | — | 账户编码模糊匹配（icontains，**注意：不是币种 code**） |
| `name` | string | — | 账户名称模糊匹配（icontains，**注意：不是币种名**） |
| `account_owner` | string | — | 开户主体名称；多值用英文逗号（如 `"alpha,beta"`） |
| `uid` | string | — | 交易所侧 UID 精确匹配 |
| `tag` | string | — | 账户标签；多值用英文逗号 |
| `market` | string | — | 平台 ID；多值用英文逗号（见 §Market ID 映射） |
| `address` | string | — | 账户地址模糊匹配 |
| `status` | string | — | 账户业务状态精确匹配（常见 `"1"` 启用） |
| `enable_status` | int | — | 启用状态精确匹配（`1` 启用 / `2` 关闭 / `3` 待启用 / `0` 未配置） |
| `ordering` | string | `-value` | 排序，`-` 前缀降序。可选：`id` / `code` / `name` / `market` / `status` / `enable_status` / `value` / `account_owner` / `vip_level` |
| `page_num` | int | `1` | 页码（≥ 1） |
| `page_size` | int | `50` | 每页条数。前端可选 50/100/150/200，服务端最大 1000 |

### 用户输入解析

- 用户给账户名 / 账户名片段（如 `alpha-bn-spot`、`mss0009`）→ `name=<原文>` 模糊匹配（icontains，不区分大小写）
- 用户给账户编码（如 `Mss0009`）→ `code=<原文>` 模糊匹配
- 用户给「市场名」（Binance/OKX/...）→ 查 §Market ID 映射转 ID 后传 `market=<id>`
- 用户给开户主体名（如 `alpha`、`alpha,beta`）→ `account_owner=<原文>` 多值逗号
- 用户给交易所侧 UID（数字字符串）→ `uid=<原文>` 精确匹配
- 用户给 `top N` / `前 N` → `page_size=min(N, 1000)`；超过 1000 截断并在尾部标注「服务端最大 1000 条」
- 用户给「估值降序」「按 USD 排」→ `ordering=-value`（默认行为）；给「VIP 等级最高」→ `ordering=-vip_level`
- 用户未指定任何过滤 → 直接默认调用（`page_num=1, page_size=50, ordering=-value`）

## 工作流程

### Step 0 — 解析用户输入

按 **§输入参数 → 用户输入解析** 抽取过滤字段；市场名按 **§Market ID 映射** 转 ID。**字段无法识别 → 不传，不追问**。

### Step 1 — 调用主接口

由 agent loop 发起 MCP 工具调用（中台接入后 `middle__` 对应 middle-mcp server_id）：

```text
tool: middle__cex_list_exchange_rate_accounts
args: {"page_num": <int>, "page_size": <int>, "ordering": "<str>",
       "id": <int?>, "code": "<str?>", "name": "<str?>",
       "account_owner": "<str?>", "uid": "<str?>", "tag": "<str?>",
       "market": "<str?>", "address": "<str?>",
       "status": "<str?>", "enable_status": <int?>}
```

只把**有值的**字段保留在 JSON 里，不要的 key 直接省略（不要传 `"key": null` 或 `"key": ""`）。

### Step 2 — 解析返回结构

中台返回固定结构 `{count, total_pages, current_page, results[]}`：

| 顶层字段 | 含义 |
|---------|------|
| `count` | 命中总条数 |
| `total_pages` | 总页数 |
| `current_page` | 当前页码 |
| `results` | 账户列表（每条字段见 §Step 3） |

### Step 3 — 字段映射（中文化展示）

| 展示列 | 字段名 | 备注 |
|--------|--------|------|
| 账户 ID | `id` | |
| 账户编码 | `code` | |
| 账户名称 | `name` | |
| 平台 | `market` | 数字 ID → 用 §Market ID 映射反查名称展示 |
| 资产/USD | `value` | **原字面**，不做精度加工 |
| 开户主体 | `account_owner` | |
| Level | `vip_level` | Deribit (market=44) 仅供参考 |
| 账户状态 | `status` | `"1"` 启用；其它见后端字典 `assets_account_status` |
| 启用状态 | `enable_status` | `1` 启用 / `2` 关闭 / `3` 待启用 / `0` 未配置（int）|
| UID | `uid` | 交易所侧 UID |
| 标签 | `tag` | |

字段缺失（key 不存在或值为 `null`）→ 单元格留空，不写 `null` / `undefined` / `0` 占位。

### Step 4 — 渲染输出

固定 Markdown 表格，列顺序：

```
| 账户 ID | 账户编码 | 账户名称 | 平台 | 资产/USD | 开户主体 | Level | 账户状态 | 启用状态 |
|---------|---------|---------|------|---------|---------|-------|---------|---------|
```

**渲染规则**：

- `资产/USD`（`value`）：**原字面输出**，禁止 `round()` / `float()` / 千分位转换（中台高精度字符串）
- `平台`：先反查 Market ID 映射拿名称，找不到则展示 `market#<id>`
- `账户状态` / `启用状态`：展示中文字典值（`"1"=启用` / `"2"=关闭` / ...），未知码原样展示
- 表格末尾追加总览：`共 N 条，当前显示 第 X 页 / 共 Y 页（按 <ordering> 排序）`
- 市场名识别降级提示（命中失败/多义）追加到表格下方独立一行，前缀 `ℹ️`

### Step 5 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| 用户输入无法解析为任何过滤字段 | 仍按默认参数查询，**不报错、不追问** |
| stderr 含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| stderr 含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| 工具未注册 / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}`，提示运维核查（cex_list_exchange_rate_accounts 真实存在，触发此错说明 middle-mcp 未注册到 fleetent 或工具清单异常） |
| stderr 含 `timeout` / `connection refused` | 重试 1 次；仍失败 → `{status:"error", reason:"upstream_timeout"}` |
| 返回结构无 `results` 字段 | `{status:"error", reason:"unexpected_response_shape", sample:<前 200 字符>}` |
| `results` 为空数组 | 不报错，直接回复「未查到符合条件的 CEX 母账户（过滤条件：...）」 |
| 其它非 0 退出 | 透传 stderr → `{status:"error", reason:"upstream_error", upstream_message:<stderr>}` |

## 输出示例

```
| 账户 ID | 账户编码 | 账户名称       | 平台    | 资产/USD     | 开户主体 | Level | 账户状态 | 启用状态 |
|---------|---------|---------------|---------|-------------|---------|-------|---------|---------|
| 1204    | Mss0009 | alpha-bn-spot | Binance | 90,123.4521 | alpha   | 7     | 启用    | 启用    |
| 1205    | Mss0010 | alpha-okx-uta | OKX     | 45,678.1234 | alpha   | 5     | 启用    | 启用    |

共 128 条，当前显示 第 1 页 / 共 3 页（按 -value 排序）
ℹ️ 市场名 `Backpack` 未识别，已忽略过滤
```

空结果时：

```
未查到符合条件的 CEX 母账户（过滤条件：market=4, account_owner=alpha）。
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `cex_list_exchange_rate_accounts` | 主接口，CEX 母账户费率管理列表 |

> 工具命名详情、参数清单、字段映射见 `common-middle-system-query/references/common-tool-naming.md` §2.5。

## 不做（边界）

- 不做估值口径转换（USD → CNY/HKD 等法币换算）—— 法币汇率走 `exchange_rate_get_exchange_rate_report`
- 不做单账户的费率/提币/借贷详情查询 —— 走 `cex_get_account_*`（待新建 spoke）
- 不做跨账户对比分析（应交给监控类 skill）
- 不查 NS / 其它系统数据（本 skill 仅查中台 middle）
- 不创建 / 修改任何记录（只读 GET）

## 本 skill 文件结构

```
skills/bs-exchange-rate/
├── SKILL.md           # 本文件
└── SKILL.tests.yaml   # trigger / non-trigger / DoD 测试
```

> NOTE (fleetent): 原 hub wrapper（`common-middle-system-query/scripts/middle-call.sh`）是 OpenClaw/Hermes 的 mcpfast 入口；fleetent 不需要 wrapper，MCP 调用由 agent loop 直接发起（`middle__<tool>`）。中台 middle-mcp 接入前本 skill 不可执行。
