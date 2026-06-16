# 中台 MCP 工具清单与命名规则

> 数据来源：中台 `middle` MCP server 实拉工具清单，2026-05-29，**19 个 tool**。
> 服务器端：`https://middle-mcp.antalpha-mo.com/mcp`。
> NOTE (fleetent): `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内；fleetent 里以 `middle__<tool_name>` 直接调用。下列工具名即 `<tool_name>` 部分。

## 1. 命名规则

```
<domain>_<verb>_<resource>
```

- `domain`：API 业务域，与 OpenAPI tag 一致（`common` / `account` / `balance` / `exchange_rate` / `cex` / `transaction` / `white` / `customer_white`）
- `verb`：`list`（多条列表）/ `get`（单条详情）
- `resource`：实际查询的资源单数或复数（不严格统一，以 server 暴露名为准）

## 2. 完整工具清单（按 domain 分组）

### 2.1 `common_*` — 公共字典（4 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `common_list_chains` | — | `limit` (default 50) | 区块链网络列表，按显示优先级排序 |
| `common_get_chain` | — | `chain_id` 或 `name`（二选一，如 ETH/BSC/TRON）| 单条链详情 |
| `common_list_coins` | — | `is_active`、`limit` | 币种列表 |
| `common_get_coin` | — | `coin_id` 或 `name`（如 BTC/ETH/USDT） | 单个币种详情 |

### 2.2 `account_*` — 账户主数据（2 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `account_list_accounts` | — | `status` / `account_type`（1普通 2子 3母）/ `market_id` / `enable_status`（1启用 2停用）/ `uid` / `limit` | 账户列表，多条件筛选 |
| `account_get_account` | — | `account_id` 或 `code`（二选一）| 单账户详情 |

### 2.3 `balance_*` — 账户余额（2 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `balance_get_account_balance` | — | `account_id` 或 `name`（精确匹配，二选一）| 实时资产快照，按子账户类型分组（spot / vip_loan / future / cross_margin / funding / savings / ...） |
| `balance_get_account_balance_snapshot` | `snapshot_time`（格式 `YYYY-MM-DD HH:MM`，**必须 15 分钟整点**：00/15/30/45）| `account_id` 或 `name` | 历史资产快照（15 分钟粒度） |

返回 JSON 包含 `balances[]`，每个子账户类型有独立 `field_template` 解释字段语义。**严禁猜字段**：永远以返回里的 `field_template` 为准展示。

### 2.4 `exchange_rate_*` — 法币汇率（1 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `exchange_rate_get_exchange_rate_report` | `base`（ISO 4217 如 SGD/USD）、`quote`（如 HKD/CNY）| `start_year` / `start_month` / `end_year` / `end_month`（不传默认当前年 1-12 月）| 生成法币历史汇率 Excel：每日明细 + 整体平均 + 每月平均 |

### 2.5 `cex_*` — 数字货币 CEX 账户费率/借贷（4 个）

覆盖 6 家交易所母账户：**Binance / OKX / Bitget / Gate / Bybit / Deribit**。

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `cex_list_exchange_rate_accounts` | — | `id`(int) / `code`(str icontains) / `name`(str icontains) / `account_owner`(str 开户主体名，多值逗号如 `"alpha,beta"`) / `uid`(str) / `tag`(str, 多值逗号) / `market`(str, 多值逗号如 `"1,4,10"`) / `address`(str icontains) / `status`(str) / `enable_status`(**int** 1/2/3/0) / `ordering`(str, 默认 `-value`) / `page_num`(int, 默 1) / `page_size`(int, 默 50, 可选 50/100/150/200, 上限 1000) | 账户费率管理列表（仅母账户 `account_type=3`），中台「账户管理 → 数字货币账户 → 账户费率管理」 |
| `cex_get_account_trade_fee` | `account_id` | `refresh`（默 false, true 强制刷新缓存） | 交易费率明细。返回 PageView，**每家交易所表格数/字段差异巨大**（详见工具 docstring） |
| `cex_get_account_withdraw_limit` | `account_id` | `refresh` | 提币额度明细（链路 / 日额度 / 手续费 / 是否需 Tag 等，跨交易所列差异大） |
| `cex_get_account_borrow_info` | `account_id` | `refresh` | 借款相关信息（VIP 借币额度 / 在借订单 / 杠杆可借 / 历史利率），合并多份底层 API |

⚠️ `cex_get_*` 三接口因底层交易所限频，后端默认每小时缓存一次。`refresh=true` 仅尝试刷新（前端按钮已禁用，是否生效以后端为准）。OKX/Bybit 的数据超时未采集会异步触发后台采集，返回标题含「采集中」的空表，需稍后重试。

### 2.6 `transaction_*` — 动账流水（2 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `transaction_list_account_transactions` | **`account_id` 或 `account_code` 二选一必填**（后端防全表扫描）| `account_name`（前缀）/ `market_id`（多值逗号）/ `address` / `tx_id`（精确）/ `code_name` / `chain_name` / `base_code` / `base_chain` / `transactions_type`（1充值 2提现 3母子划转 4账户内划转 6手录入收入 7手录入支出）/ `status` / `tag` / `project_id` / `project_code` / `partner_company` / `account_owner` / `account_nature`（1普通 2子 3母）/ `tx_start_time` / `tx_end_time` / `amount_start` / `amount_end` / `alert_level` / `exposure_type` / `ids` / `id` / `ordering`（默 `-date`）/ `page_num` / `page_size`（默 50, 上限 200） | V2 动账流水列表。覆盖充值/提现/划转/手录入；附 TxnID 风险等级、关联来源/目标账户、NS 流程关联 |
| `transaction_get_transaction_detail` | `transaction_id` | — | 单条流水详情，比 list 额外多 `transfer_tag` / `ns_mail_title` / `amount`（绝对值）/ `fee` / `info` 等 |

字典约定：
- `market_id`：Binance=4 / OKX=10 / Bybit=19 / Bitget=42 / Gate=43 / Deribit=44（其它链类 ID 见 `common_list_chains`）
- `status`：`'1'` 成功；其它见后端字典 `flow_status_list`
- `alertLevel`：`'5'` 无风险（默认）

### 2.7 `white_*` — 内部白名单（2 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `white_list_whitelist` | — | `address`（icontains）/ `subject`（icontains）/ `coin`（精确）/ `chain_id` / `market_id` / `audit_status`（1-6）/ `state`（1正常 2归档 3废弃 4黑名单）/ `page` / `page_size`（默 20, 上限 100） | 内白名单列表，所有 FK 返回 `{id, code, name}`，枚举附 `*_display` 中文 |
| `white_get_whitelist` | `whitelist_id` | — | 内白名单详情，比 list 多 8 字段：`remark` / `msg` / `fingerprint` / `address_tag` / `uid` / `deposit_address` / `tag_info` / `account_owner` |

### 2.8 `customer_white_*` — 客户白名单（2 个）

| 工具 | 必填 | 可选 | 用途 |
|------|------|------|------|
| `customer_white_list_customer_whitelist` | — | `address` / `customer_id` / `customer_name`（模糊）/ `coin`（精确）/ `chain_id` / `business_id` / `risk`（0-4）/ `page` / `page_size`（默 20, 上限 100） | 客户白名单列表。后端隐式过滤：`is_delete=0` + `audit_status=60`（终审通过） + `state="1"`（正常）+ 部门归属 |
| `customer_white_get_customer_whitelist` | `whitelist_id` | — | 客户白名单详情，比 list 多 `description` / `remark` / `fingerprint` / `email_title` / `risk_reason` / `risk_updatetime` / `compliance_recommendations` |

## 3. spoke 使用映射

当前已实现的中台 spoke 使用情况：

| Spoke | 使用的中台工具 |
|-------|--------------|
| `common-middle-dict` | `common_list_chains` + `common_get_chain` + `common_list_coins` + `common_get_coin`（链/币字典）|
| `common-middle-accounts` | `account_list_accounts` + `account_get_account`（账户主数据列表 + 详情）|
| `common-middle-account-assets` | `balance_get_account_balance` |
| `bs-transaction-history` | `transaction_list_account_transactions`（主） + `balance_get_account_balance`（内部 name→id 解析）|
| `bs-exchange-rate` | `cex_list_exchange_rate_accounts`（v1.0.0 已对齐真实工具，2026-05-29 修正） |
| `bs-cex-account-details` | `cex_get_account_trade_fee` + `cex_get_account_withdraw_limit` + `cex_get_account_borrow_info`（CEX 单账户三连）|
| `bs-fiat-exchange-rate` | `exchange_rate_get_exchange_rate_report`（法币汇率 xlsx）|
| `common-middle-whitelist-internal` | `white_list_whitelist` + `white_get_whitelist`（内白名单：公司自有地址）|
| `common-middle-whitelist-customer` | `customer_white_list_customer_whitelist` + `customer_white_get_customer_whitelist`（客户白名单：外部对手方，后端隐式过滤仅终审通过）|

**当前共 17 个工具被覆盖（19 个中），剩余 2 个工具需扩展现有 spoke**：

| 能力区 | 未覆盖工具 | 后续动作 |
|--------|-----------|---------|
| 历史资产快照 | `balance_get_account_balance_snapshot` | 扩展 `common-middle-account-assets`：`fetch-assets.py` 加 `--snapshot-time` 参数（15 分钟整点 `YYYY-MM-DD HH:MM`），路由原有 `balance_get_account_balance` 或新工具 |
| 流水详情 | `transaction_get_transaction_detail` | 扩展 `bs-transaction-history`：`render_xlsx.py` 加 `--transaction-id` 参数，单条详情走新工具 |

## 4. 命名陷阱与历史误解

- **不存在的工具名**：`market_list_market` / `account_list_account_exchange_rate_data` 均不存在（曾出现在 `bs-exchange-rate` 早期文档中，2026-05-29 已修正）。**所有"市场"概念现在通过 `cex_list_exchange_rate_accounts.market` 数字 ID + 硬编码映射表使用**，没有单独的 list_market 工具
- **市场 ID 硬编码映射**（取自 `cex_list_exchange_rate_accounts` 工具 docstring）：Binance=4 / OKX=10 / Bybit=19 / Bitget=42 / Gate=43 / Deribit=44
- **`is_active`、`enable_status`、`status` 三个概念别混**：分别对应「币种/链是否激活」「账户是否启用」「账户业务状态」
- **复数/单数无规律**：`account_list_accounts`（复）但 `common_list_chains`（复）vs `transaction_list_account_transactions`（复），`account_get_account`（单）vs `common_get_chain`（单）——以 `middle` server 实拉为准
- **`code` / `name` 在不同 domain 含义不同**：在 `cex_list_exchange_rate_accounts` / `account_list_accounts` 里是**账户编码 / 账户名称**；在 `common_get_coin` / `common_get_chain` 里是**币种符号 / 链代码**。不要跨域复用语义假设
- **白名单两套别混**：`white_*` 是**内白名单**（公司内部地址）；`customer_white_*` 是**客户白名单**（外部对手方地址）。审批/隐式过滤逻辑不同

## 5. 新增工具流程

中台 OpenAPI 新增端点后：

1. 中台 `middle` MCP server 发布新版本（自动从 OpenAPI 推导工具名）
2. agent 端拉一次 `middle` server 工具清单
3. 在本文件 §2 对应 domain 下登记，必填 / 可选参数从 docstring 提取
4. 若新工具属于现有 spoke 能力域，在 §3 的"未覆盖工具"行打 ✓；若需要新 spoke，按 hub 路由表 §路由表 增加分支

## 6. 调用方式

复读一遍 hub SKILL.md 的约定：fleetent 里中台查询是**直接的 MCP 工具调用**，工具名 = `middle__<tool_name>`（双下划线），参数以结构化 JSON 对象传入。

```jsonc
// 工具 middle__<tool_name>，参数对象：
{ ... }  // 无参数传空对象 {}
```

numeric-looking ID 字段（`uid` / `market` / `tag` 等）必须显式带引号传字符串——见 `wrapper-caveats.md` §1、§5。
