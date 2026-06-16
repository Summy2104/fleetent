---
name: common-middle-dict
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台链/币种字典查询（middle-mcp `common_list_chains` /
  `common_get_chain` / `common_list_coins` / `common_get_coin`）。
  按显示优先级返回区块链网络与币种基础字典，支持按 ID 或代码取单条详情。
  典型用途：把链代码（ETH/BSC/TRON）/币种符号（BTC/ETH/USDT）转 ID，
  做主数据补全或上下游 spoke 的 ID→名称映射依赖。
  仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: RD Team
  version: 1.0.0
complexity: L1
---

# 中台链/币种字典查询（Common Dictionary）

> ⛔ **执行前强制约束**（hub `common-middle-system-query` §共通强制约束的子集）
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 `middle` MCP server 自身配置注入。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **MCP 调用方式**：中台查询是 fleetent 直接工具调用，工具名 `middle__<tool_name>`，numeric-looking ID 字段必须显式带引号传字符串（见 hub `wrapper-caveats.md` §1、§5）。

> NOTE (fleetent): 中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内；下文工具名、参数、路由逻辑按 fleetent 直接调用约定（`middle__<tool_name>`）保留，运行前需在 my-bot 挂载该 server。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "中台支持哪些链" / "区块链网络列表" / "ETH 在中台是什么 ID"
  - "中台有哪些币种" / "USDT 属于哪个币种 ID" / "已激活的币列出来"
- **被其它 spoke 引用**：上下游 spoke 在做"链/币种名 → ID"映射时优先调用本 skill（避免硬编码字典）。

## 能力边界

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 列出中台已配置的区块链网络 / 币种 | ✅ | — |
| 按 chain_id 或链代码查单条链详情 | ✅ | — |
| 按 coin_id 或币种符号查单条币种详情 | ✅ | — |
| 账户列表 / 账户详情 | ❌ | `common-middle-accounts` |
| 账户资产 / 余额 | ❌ | `common-middle-account-assets` |
| 动账流水 | ❌ | `bs-transaction-history` |
| 法币汇率 / 估值换算 | ❌ | `bs-fiat-exchange-rate` |
| CEX 费率管理 | ❌ | `bs-exchange-rate` |

## 调用模式

所有中台查询都是 fleetent 直接 MCP 工具调用：工具名 `middle__<tool_name>`，参数以结构化 JSON 对象传入。

**示例**（工具名 + 参数对象）：

```jsonc
// 1) 列前 50 个链 —— 工具 middle__common_list_chains
{ "limit": 50 }

// 2) 按链代码查详情 —— 工具 middle__common_get_chain
{ "name": "ETH" }

// 3) 列已激活币种 —— 工具 middle__common_list_coins
{ "is_active": true, "limit": 100 }

// 4) 按币种符号查详情 —— 工具 middle__common_get_coin
{ "name": "USDT" }
```

## 输入参数

### `common_list_chains`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `limit` | int | `50` | 返回的最大数量 |

### `common_get_chain`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `chain_id` | int | 二选一 | 链主键 ID |
| `name` | string | 二选一 | 链代码，如 `ETH` / `BSC` / `TRON` |

> `chain_id` 与 `name` 二选一必填，全不传 → 报错追问。

### `common_list_coins`

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `is_active` | bool | — | 激活过滤（`true`=仅已激活 / `false`=仅未激活 / 不传=全部）|
| `limit` | int | `50` | 返回的最大数量 |

### `common_get_coin`

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `coin_id` | int | 二选一 | 币种主键 ID |
| `name` | string | 二选一 | 币种符号，如 `BTC` / `ETH` / `USDT` |

> `coin_id` 与 `name` 二选一必填。

## 用户输入解析

- 用户给「列出所有链 / 区块链网络」→ `common_list_chains limit=50`
- 用户给「列出所有币种」→ `common_list_coins limit=50`
- 用户给「已激活 / 在用」币种 → `common_list_coins is_active=true limit=50`
- 用户给纯数字（如 `1`）+ 链/币上下文 → 走对应 `get_chain` / `get_coin` 的 `*_id`
- 用户给链代码（大写字母组合如 `ETH` / `BSC` / `TRON`）→ `common_get_chain name=<原文>`
- 用户给币种符号（大写字母组合如 `BTC` / `USDT`）→ `common_get_coin name=<原文>`
- 用户给 `top N` / `前 N` → `limit=N`
- 用户上下文模糊（仅一个大写字母组合，不确定是链还是币）→ 优先按币种查 `common_get_coin`，失败再回退到 `common_get_chain`，并在尾部 `ℹ️` 标注「自动按币种解析」

## 工作流程

### Step 0 — 路由判断（list vs get / chain vs coin）

- 用户问"链"相关 → chain 路径
- 用户问"币种 / 代币"相关 → coin 路径
- 用户给具体代码（`ETH` / `USDT`）→ `get_*` 路径；上下文模糊则按 §用户输入解析 兜底

### Step 1 — 调用主接口

```jsonc
// 4 种工具选其一（工具名 middle__<tool>，参数对象）
// middle__common_list_chains : { "limit": <n> }
// middle__common_get_chain   : { "chain_id": <n> } 或 { "name": "<str>" }
// middle__common_list_coins  : { "is_active": <bool>, "limit": <n> }
// middle__common_get_coin    : { "coin_id": <n> } 或 { "name": "<str>" }
```

### Step 2 — 字段映射

中台返回字段以 OpenAPI 为准。常见字段（**实拉后由 references 登记**；首次调用时按下表兜底）：

| 展示列 | 字段名 |
|--------|--------|
| 链 ID / 币种 ID | `id` |
| 链代码 / 币种符号 | `name` 或 `code` |
| 全称 | `full_name` 或 `chain_name` / `coin_name` |
| 是否激活 | `is_active` |
| 显示优先级 | `priority` 或 `order` |

字段缺失 → 单元格留空，不写 `null` / `undefined` / `0` 占位。

### Step 3 — 渲染输出

**列表模式**：Markdown 表格 + 末尾 `共 N 条（limit=<N>）` 总览。

**详情模式**：键值表逐字段展开。

### Step 4 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `common_get_chain` / `common_get_coin` 既没传 `*_id` 也没传 `name` | 直接报错追问 |
| 工具返回含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| 工具返回含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| 工具返回含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| 工具返回含 `timeout` / `connection refused` | 重试 1 次 |
| 列表返回为空 | 不报错，回复「未查到字典条目（过滤：...）」 |
| 详情查不到 | 「链/币种 `<X>` 不存在或未配置」 |
| 其它错误 | 透传错误信息 |

## 不做（边界）

- 不做账户/余额/流水/费率查询（见 §能力边界）
- 不做链上数据查询（如 RPC 余额、区块浏览器）—— 本 skill 只查中台已登记的字典
- 不创建 / 修改任何字典条目（只读 GET）

## 本 skill 文件结构

```
skills/common-middle-dict/
├── SKILL.md
└── SKILL.tests.yaml
```

> MCP 调用约定收敛在 hub `common-middle-system-query`（`middle__<tool_name>` 直接调用），工具清单见 `common-middle-system-query/references/common-tool-naming.md` §2.1。
