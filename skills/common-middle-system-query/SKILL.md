---
name: common-middle-system-query
description: >
  中台（middle）数据查询的「路由与公共规范」入口。承载 MCP 调用约定、
  工具命名规则、共通输出规范与错误码。涉及中台账户主数据 / 账户资产 /
  动账流水 / CEX 母账户费率 / CEX 账户详情 / 法币汇率 / 链币字典 /
  白名单查询的请求触发本 skill，由本 skill 路由到对应子 skill：
  common-middle-dict / common-middle-accounts / common-middle-account-assets /
  bs-exchange-rate / bs-cex-account-details / bs-transaction-history /
  bs-fiat-exchange-rate / common-middle-whitelist-internal /
  common-middle-whitelist-customer。
  触发词：中台查询、middle 查询、查中台、列出账户、账户列表、账户类型、
  母账户、子账户、账户编码、账户 ID、账户 UID、UID 查账户、按 UID 查、
  账户基本信息、账户资产、子账户资产、账户持仓、批量账户资产、账户动账、
  动账流水、账户出入账、账户进出账、xlsx 流水导出、CEX 母账户、
  账户费率管理、账户 USD 估值、VIP 等级、交易费率、提币额度、借贷信息、
  借币利率、法币汇率、FX 汇率、USD CNY、SGD HKD、区块链网络列表、
  币种列表、内白名单、公司白名单、客户白名单、外部对手方白名单、白名单地址。
  直接指明单一意图（"列母账户""导动账流水""查持仓""查 CEX 母账户列表"
  "查交易费率""查法币汇率""查内白名单""查客户白名单"）也由本 skill 接管，
  内部路由到子 skill；子 skill 不应被独立触发。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# 中台内部系统查询 — 路由与公共规范

通过 `middle` MCP server 连接中台（`middle.antalpha-mo.com`）的账户域数据查询。本 skill 是**父 skill**，承担：

1. **MCP 调用约定**（fleetent 直接工具调用，工具名 `middle__<tool_name>`）
2. **工具命名规则**（OpenAPI → MCP 自动生成 + 兜底候选表）
3. **共通规范**（数值精度 / 字段展示 / 文件交付 / 安全约束）
4. **路由到子 skill**（具体业务逻辑下放子 skill）

> NOTE (fleetent): 中台 `middle` MCP server（`middle.antalpha-mo.com`，本文及子 skill 引用的 `balance_get_account_balance` / `account_list_accounts` 等 19 个 GET 工具）当前不在 my-bot 已挂载的 MCP 清单内。下文工具名、参数、路由逻辑均按 fleetent 直接调用约定（`middle__<tool_name>`）保留；实际运行前需在 my-bot 挂载该 `middle` server。

## 路由表（父 → 子）

| 用户表述范围 | 触发子 skill | 关键判别词 |
|-------------|-------------|-----------|
| 链 / 币种字典（中台已配置的链/币种列表与详情）| `common-middle-dict` | 字典查询，做 ID→名称映射 |
| 账户主数据（列表 / 单条详情，按 account_type / market / enable_status / **UID** 过滤；按 account_id / code 查详情）| `common-middle-accounts` | 关注"账户存不存在 / 是什么类型 / UID 是谁 / UID 反查账户"，不关心余额或估值。**`account_list_accounts.uid` 是 middle 支持 UID 查账户的主入口** |
| 账户当前持有 / 可用 / 冻结资产 / 批量账户资产 / 持仓 | `common-middle-account-assets` | 无时间范围、关注"现在持有多少" |
| 账户某段时间的资金进出明细 / xlsx 流水导出 | `bs-transaction-history` | 有时间范围、需要 xlsx 文件 |
| CEX 母账户费率管理列表 / 账户 USD 估值排行 / 账户 VIP 等级 | `bs-exchange-rate` | 列出 6 家 CEX 母账户（一行一账户），含估值 + VIP |
| CEX 单账户**详情**（交易费率 / 提币额度 / 借贷信息）| `bs-cex-account-details` | 按 `account_id` 取费率/限额/借贷三类详情 |
| 法币历史汇率报告（SGD/HKD、USD/CNY 等 ISO 4217 配对）| `bs-fiat-exchange-rate` | 输出 xlsx，含每日 + 整体平均 + 每月平均 |
| **内**白名单查询（WhiteListV2，公司内部地址 / 主体）| `common-middle-whitelist-internal` | 仅查询，起草请改用 NS 侧 `bs-internal-whitelist-drafting` |
| **客户**白名单查询（CustomerWhiteList，外部对手方 / 含风险评级）| `common-middle-whitelist-customer` | 仅查询，协同请改用 NS 侧 `bs-external-whitelist-coordinating` |

**决策树**：

1. 用户提到「时间范围」或「最近 N 天」「上周」「Q1」等 → `bs-transaction-history`
2. 用户提到「CEX 母账户列表」「账户费率管理」「按估值排序」「VIP 等级」 → `bs-exchange-rate`
3. 用户提到「单账户费率/手续费/提币额度/借贷信息」（有 account_id 上下文）→ `bs-cex-account-details`
4. 用户提到「法币 / FX / ISO 代码对（USD/CNY 等）/ 汇率报告」→ `bs-fiat-exchange-rate`
5. 用户提到「账户持有」「余额」「可用 / 冻结」「资产快照」「持仓」 → `common-middle-account-assets`
6. 用户提到「列出账户」「账户类型 / 主子账户」「账户编码 / ID / UID 是什么」「账户基本信息」 → `common-middle-accounts`
7. 用户提到「链 / 币种 / 区块链 / 代币字典」→ `common-middle-dict`
8. 用户提到「内白名单 / 公司白名单 / 公司主体地址」→ `common-middle-whitelist-internal`
9. 用户提到「客户白名单 / 外部对手方 / 客户地址 / 高风险地址」→ `common-middle-whitelist-customer`
10. 用户裸说「白名单」无限定词 → **反问** "内白名单 还是 客户白名单"（不默认猜）
11. 用户要**起草**白名单邮件 / **协同**外部白名单流程 → NS 侧 `bs-internal-whitelist-drafting` / `bs-external-whitelist-coordinating`
9. 同时涉及多个维度 → 先按主诉求路由，必要时串行调用多个子 skill

**当前未覆盖的中台能力**（详见 `references/common-tool-naming.md` §3）：

- 历史资产快照（15 分钟粒度）→ `balance_get_account_balance_snapshot` 待 `common-middle-account-assets` 加 `--snapshot-time` 扩展
- 流水详情（单条）→ `transaction_get_transaction_detail` 待 `bs-transaction-history` 加 `--transaction-id` 扩展

**显式划走 NS 侧的场景**（**不要**尝试在中台路由）：

- **按 TxID 查到账状态**（"这笔到账了吗"、"TXID xxxx 是否到账"、"查 tx hash 的资金到账"）→ 走 NS 侧 `common-ns-flows`。中台 `transaction_list_account_transactions.tx_id` 必须配合 `account_id`/`account_code`，做不了纯 TxID 全局反查；NS `r_transactions.txid` 支持无账户上下文反查，是这个场景的唯一正确入口
- 客户 / 项目 / 业务线 / 流程审批 / KYC → 全部走 NS 侧对应 spoke

遇到以上意图，hub 应在响应中说明"中台 API 支持但尚无 spoke 封装"并退化建议，**不要**强行用现有 spoke 兜底。

## 共通强制约束（所有子 skill 继承）

1. **严禁** 直接 `curl` 中台 HTTP 端点（`https://middle-mcp.antalpha-mo.com/mcp`）；`X-API-Key` 由 `middle` MCP server 自身按其配置注入，agent 不持有 Token
2. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段
3. **数值精度零加工**：金额 / 余额 / 汇率原字面输出，禁止 `round()` / `float()` / 千分位 / `f"{x:.Nf}"` 等格式化操作。Python 脚本内部用 `parse_float=str` 锁字面
4. **严禁直连 HTTP**：所有中台查询必须经 `middle__<tool_name>` MCP 工具调用；禁止在 Python 内 `subprocess.run(["curl", ...])` 或自行拼 HTTP 请求绕过 MCP
5. **文件交付**：xlsx 等输出文件必须通过 `send_file` 发回当前对话；严禁向用户透露内部文件路径（如 `/tmp/...` 字面）
6. **空结果仍交付文件**：rows=0 时脚本会生成只有表头的 .xlsx，必须用 `send_file` 发回，不允许只回文字打发用户

## 调用约定

**【MCP 调用方式】** 所有中台查询都是 fleetent **直接工具调用**，工具名 = `middle__<tool_name>`（双下划线），参数以结构化 JSON 对象传入：

```jsonc
// 工具 middle__<tool_name>，参数对象：
{ ... }
```

> **ID 字段类型纪律**：详见 `common-mcp-guide`。中台 OpenAPI 把 `uid` / `account_owner` / `market` / `tag` / 多值逗号串等字段标为 str，其值常是纯数字字符串（`uid="123456"`、`market="4,10"`）。务必在工具参数里把这些字段显式传成**带引号的字符串**，不要传成整数，否则服务端返回空结果（`results: []`）或 type error。

**示例**（工具名 + 参数对象）：

```jsonc
// 拉链字典 —— 工具 middle__common_list_chains
{ "limit": 50 }

// 拉 CEX 母账户费率管理列表 —— 工具 middle__cex_list_exchange_rate_accounts
// 多值 market 保持字符串
{ "market": "4,10", "page_num": 1, "page_size": 50, "ordering": "-value" }

// 查账户实时资产 —— 工具 middle__balance_get_account_balance
{ "name": "bntrad8@nsdigital.io" }

// 按 UID 查账户 —— 工具 middle__account_list_accounts
// uid 是数字串，必须带引号
{ "uid": "123456", "limit": 50 }

// 拉账户动账流水 —— 工具 middle__transaction_list_account_transactions
{ "account_id": 1204,
  "tx_start_time": "2026-04-29 00:00:00",
  "tx_end_time": "2026-05-19 23:59:59",
  "ordering": "-date", "page_size": 200 }
```

> 完整工具清单（19 个）按 domain 分组的详细参数、必填/可选、字段映射，见 `references/common-tool-naming.md`。

**当前能力面**：每个中台工具以 `middle__<tool_name>` 直接调用，参数照传。所有错误从工具返回内容透传，按子 skill 的 reason 归类处理。

## 工具命名规则

中台 MCP 工具按 OpenAPI → MCP 自动生成规则：

```
<domain>_<verb>_<resource>
```

实际暴露 **19 个 GET 工具**，按 domain 分布：

| domain | 工具数 | 关键能力 |
|--------|--------|----------|
| `common` | 4 | 链/币字典 |
| `account` | 2 | 账户主数据（列表 + 详情） |
| `balance` | 2 | 实时余额 + 15 分钟粒度历史快照 |
| `exchange_rate` | 1 | 法币汇率 xlsx |
| `cex` | 4 | 6 家 CEX 账户费率/提币/借贷 |
| `transaction` | 2 | V2 动账流水 + 单条详情 |
| `white` | 2 | 内白名单 |
| `customer_white` | 2 | 客户白名单 |

完整工具名 / 必填可选参数 / 字段映射 / 字典编码 / 命名陷阱，**全部以 `references/common-tool-naming.md` 为准**。SKILL.md 不复述工具签名，避免漂移。

返回 `unknown tool` / `tool not found` → `{status:"error", reason:"middle_mcp_tool_missing"}`，提示运维核查 `middle` MCP server 是否同步到最新中台 OpenAPI。

## 输出规范

子 skill 展示中台返回数据时：

- **数值原字面**：金额 / 余额 / 汇率不做四舍五入、不做单位换算（USD→CNY 等估值口径转换不在本 skill 范围）
- **字段名中文化**：按 spoke 自身的 references 字段映射表展示中文列名；无中文注释的字段跳过不展示
- **时间格式**：UTC → UTC+8 展示（`bs-transaction-history` 例外：V2 接口的 `date` 字段已是 UTC+0，保留原值）
- **空结果**：明确回复"未查到符合条件的 X（过滤条件：...）"；xlsx 类输出仍交付空表头文件
- **错误透传**：按 spoke 已枚举的 reason 透传给用户，不要重新解析 stderr 文本

详细规则见 `references/common-conventions.md`。

## 端点能力索引（按子 skill 分布）

各域详细端点列表见对应子 skill 的 SKILL.md，完整工具清单见 `references/common-tool-naming.md`。

- **`common-middle-dict`**：`common_list_chains` + `common_get_chain` + `common_list_coins` + `common_get_coin`（链/币字典列表 + 详情）
- **`common-middle-accounts`**：`account_list_accounts` + `account_get_account`（账户主数据列表 + 单条详情）
- **`common-middle-account-assets`**：`balance_get_account_balance`（账户资产 + 子账户、可用 + 冻结）
- **`bs-exchange-rate`**：`cex_list_exchange_rate_accounts`（CEX 母账户费率管理列表）
- **`bs-cex-account-details`**：`cex_get_account_trade_fee` + `cex_get_account_withdraw_limit` + `cex_get_account_borrow_info`（单账户详情三连）
- **`bs-transaction-history`**：`transaction_list_account_transactions`（V2 动账流水） + `balance_get_account_balance`（内部用作 name → id 解析）
- **`bs-fiat-exchange-rate`**：`exchange_rate_get_exchange_rate_report`（法币历史汇率 xlsx）
- **`common-middle-whitelist-internal`**：`white_list_whitelist` + `white_get_whitelist`（内白名单列表 + 详情）
- **`common-middle-whitelist-customer`**：`customer_white_list_customer_whitelist` + `customer_white_get_customer_whitelist`（客户白名单列表 + 详情，后端隐式过滤仅终审通过）

**中台 MCP 总暴露 19 个 GET 工具**，当前 9 个 spoke 覆盖 17 个工具；剩余 2 个为「历史快照 / 流水详情」，需要扩展现有 spoke 的 Python 脚本支持，作为独立 follow-up PR。中台写端点不在本路由范围内。

## 错误码归类

所有中台 MCP 工具错误统一归类到以下 reason，子 skill 透传：

| 工具返回包含 | reason | 处理 |
|------------|--------|------|
| `unknown tool` / `tool not found` | `middle_mcp_tool_missing` | 尝试兜底名一次；仍失败 → 终止 |
| `unknown server` / `server not found` | `middle_mcp_not_registered` | 提示运维核查 `middle` MCP server 是否挂载 |
| `401` / `403` / `unauthorized` | `missing_or_invalid_api_key` | 提示运维补 API Key |
| `timeout` / `connection refused` | `upstream_timeout` | 自动重试 1 次 |
| 其它错误 | `upstream_error` | 透传错误信息 |

完整错误处理矩阵见 `references/wrapper-caveats.md`。

## 信任模型

**当前模型**：中台调用通过 `middle` MCP server 自身配置注入 `X-API-Key` 鉴权。agent 不接触 Token。

**凭证决定数据权限**：不同 X-API-Key 对应不同的中台权限范围，per-agent 的 `middle` server 配置确保每个 agent 只能访问自己 key 授权的数据。

**与 NS hub (`common-ns-system-query`) 的差异**：NS 侧因为涉及业务流程，要求 agent 传入 `sender_id` 做审计；中台侧目前是只读账户域数据，未引入此强校验。

## 本 skill 的引用路径

```
SKILL.md                                  # 本文件
references/common-conventions.md          # 输出规范 / 字段展示 / 数值精度
references/common-tool-naming.md          # 工具命名规则 + 兜底名表
references/wrapper-caveats.md             # 错误码 / 信任模型
```

子 skill 的 references 由对应子 skill 维护。
