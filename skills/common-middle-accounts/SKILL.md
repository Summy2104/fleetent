---
name: common-middle-accounts
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台账户主数据查询（middle-mcp `account_list_accounts` +
  `account_get_account`）。覆盖账户主数据「列表」与「单条详情」两类查询：
  按账户状态 / 类型（普通/子/母）/ 市场 / 启用状态 / UID 过滤列出账户；
  按账户 ID 或编码查询单账户基本信息。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: RD Team
  version: 1.0.0
complexity: L1
---

# 中台账户主数据查询（Account Masterdata）

> ⛔ **执行前强制约束**（hub `common-middle-system-query` §共通强制约束的子集）
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 `middle` MCP server 自身配置注入。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **MCP 调用方式**：中台查询是 fleetent 直接工具调用，工具名 `middle__<tool_name>`，numeric-looking ID 字段（如 `uid`）必须显式带引号传字符串（见 hub `wrapper-caveats.md` §1、§5）。

> NOTE (fleetent): 中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内；下文工具名、参数、路由逻辑按 fleetent 直接调用约定（`middle__<tool_name>`）保留，运行前需在 my-bot 挂载该 server。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "alpha 名下有多少个账户" / "查所有母账户" / "Binance 上有哪些账户"
  - "账户 1204 的基本信息" / "账户编码 Mss0009 是什么"
  - "列一下停用状态的账户" / "UID 12345678 对应什么账户"
- **被其它 skill 调用**：对账 / 监控类 skill 在做 ID→名称映射或子账户聚合时，需要先列出/解析单个账户的基本信息。

## 能力边界

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 列出账户主数据（id / code / name / market / type / status / uid） | ✅ | — |
| 按 ID 或编码查单账户基本信息 | ✅ | — |
| 账户当前持有 / 可用 / 冻结资产 | ❌ | `common-middle-account-assets` |
| 账户某段时间的动账明细 | ❌ | `bs-transaction-history` |
| CEX 母账户费率管理（含 USD 估值 / VIP 等级） | ❌ | `bs-exchange-rate` |
| 账户的交易费率 / 提币额度 / 借贷信息 | ❌ | `cex_get_account_*`（待新建 spoke） |

## 调用模式

所有中台查询都是 fleetent 直接 MCP 工具调用：工具名 `middle__<tool_name>`，参数以结构化 JSON 对象传入。

**示例**（工具名 + 参数对象）：

```jsonc
// 1) 列出所有母账户（账户类型 = 3）—— 工具 middle__account_list_accounts
{ "account_type": 3, "limit": 50 }

// 2) 列出 Binance 上启用状态的账户 —— 工具 middle__account_list_accounts
{ "market_id": 4, "enable_status": 1, "limit": 50 }

// 3) 按 UID 找账户（uid 是 str，必须带引号）—— 工具 middle__account_list_accounts
{ "uid": "12345678" }

// 4) 按账户主键查详情 —— 工具 middle__account_get_account
{ "account_id": 1204 }

// 5) 按账户编码查详情 —— 工具 middle__account_get_account
{ "code": "Mss0009" }
```

## 输入参数

### `account_list_accounts` 列表查询

所有字段均为可选；用户不提供时使用默认值，**不追问**直接执行。

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `status` | string | — | 账户业务状态精确匹配 |
| `account_type` | int | — | 账户类型：`1` 普通 / `2` 子账户 / `3` 母账户 |
| `market_id` | int | — | 关联市场 ID（见 §Market ID 映射） |
| `enable_status` | int | — | 启用状态：`1` 启用 / `2` 停用 |
| `uid` | string | — | 账户 UID（精确匹配） |
| `limit` | int | `50` | 返回的最大数量 |

> ⚠️ 该工具**没有分页参数**（只有 `limit`），与 `cex_list_exchange_rate_accounts` / `transaction_list_account_transactions` 的分页风格不同。如需更多结果，调大 `limit`；服务端实际上限以 `middle` server 实拉为准。

### `account_get_account` 单条详情

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `account_id` | int | 二选一 | 账户主键 ID |
| `code` | string | 二选一 | 账户唯一编码 |

> `account_id` 与 `code` **必须二选一**，全不传或同时传都不可接受。

## Market ID 映射

`account_list_accounts.market_id` 是数字 ID。**当前中台 middle-mcp 没有暴露 `list_market` 字典工具**，市场名 → ID 用下表硬编码（与 `bs-exchange-rate` 共用映射）：

| 市场名 | market_id |
|--------|-----------|
| Binance | `4` |
| OKX | `10` |
| Bybit | `19` |
| Bitget | `42` |
| Gate | `43` |
| Deribit | `44` |

链类账户（非 CEX）的 `market_id` 见 `common_list_chains` 工具返回（暂无 spoke 封装；命中失败时不传 `market_id` 退化为全市场查询）。

## 用户输入解析（字段抽取，路径由 §Step 0 决定）

本段只负责把用户原文映射到 MCP 工具参数字段；具体走哪条路径（直接 get / 直接 list / 2-step）见 §工作流程 → §Step 0 决策表。

| 用户原文形态 | 抽取字段 | 备注 |
|------------|---------|------|
| 「列出母账户 / 子账户 / 普通账户」 | `account_type=3 / 2 / 1` | 列表过滤 |
| 市场名（Binance/OKX/Bybit/Bitget/Gate/Deribit）| `market_id=<硬编码 ID>` | 见 §Market ID 映射；未识别 → 不传 |
| 「停用」/「启用」 | `enable_status=2 / 1` | 列表过滤 |
| 「待启用」/「未配置」 | `enable_status=3 / 0` | 列表过滤 |
| 纯数字（语境为账户主键，如「账户 1204」「id=1204」）| `account_id=<n>` | → 路径 A 直接 get |
| 公司编码格式（如 `Mss0009`、含「账户编码」「code」前缀）| `code=<原文>` | → 路径 A 直接 get |
| 账户名 / 邮箱形态（如 `alpha-bn-spot`、`bntrad8@nsdigital.io`、含「账户名」前缀）| `name=<原文>` | → 路径 C 2-step（先 balance 解析）|
| 纯数字（语境为交易所 UID，如「UID 12345678」「交易所侧 ID」）| `uid=<原文>` | → 路径 B 列表或路径 D 2-step（按"详情"意图决定）|
| 「top N」/「前 N」 | `limit=N` | 仅 list 模式有效（路径 B/E），路径 A/C/D 无 limit |
| 未指定任何过滤 | — | 默认路径 B `account_list_accounts limit=50` |

**关键消歧规则**：

1. **纯数字的双义性**：用户说"查 1204" 时如何区分账户主键（`account_id`）vs UID？
   - 上下文含「账户 N」「id N」「主键」→ `account_id`
   - 上下文含「UID N」「交易所 UID」「Binance UID」→ `uid`
   - 无任何上下文（用户只丢一个数字）→ 默认按 `account_id` 走路径 A；如 404 再以 `uid=<原文>` 重试路径 D
2. **`code` vs `name` 的双义性**：用户说"查 alpha-bn-spot" 时归 code 还是 name？
   - 公司内部编码格式（如 `Mss0009`、`ZYJDW00203-B5` 等大写字母+数字组合）→ `code`
   - 描述性 / 含 `@` 邮箱 / 含 `-` 多段 / 小写为主 → `name`
   - 仍模糊 → 优先按 `code` 走路径 A（单次 get 成本低）；返回 404 再退化按 `name` 走路径 C
3. **同时给了 id 和 code/name** → 优先 id，其余忽略，`ℹ️` 标注

## 工作流程

### Step 0 — 路由判断

按 §用户输入解析 抽出用户给的所有字段，按下表选路径。`account_get_account` 接受 `account_id` 或 `code`（二选一）；其它过滤参数（`name` / `uid` / `account_type` / `market_id` / `status` / `enable_status`）**必须 2-step 解析**才能拿到单条详情。

| 用户给的标识 / 过滤 | 用户意图 | 路径 |
|------|---------|------|
| `account_id`（纯数字主键）| 任意 | **直接** `account_get_account account_id=<n>`（单次调用）|
| `code`（账户编码，如 `Mss0009`）| 任意 | **直接** `account_get_account code=<str>`（单次调用）|
| `name`（账户名 / 邮箱形态，如 `alpha-bn-spot`）| 任意 | **2-step (name→id)**：`balance_get_account_balance name=<str>` 解析 `account_id` → `account_get_account account_id=<n>`（`account_list_accounts` **无 `name` 过滤**，必须借 balance 接口做 name 解析）|
| `uid`（交易所侧 UID）| 详情（含"详情" / "信息"关键词）| **2-step (uid→id)**：`account_list_accounts uid=<str>` → 命中唯一取 id → `account_get_account account_id=<n>`；命中多条列候选；零命中报错 |
| `uid` | 列表（"哪些账户" / "列举"）| **直接** `account_list_accounts uid=<str>` 返回列表 |
| 过滤组合（`account_type` / `market_id` / `status` / `enable_status`）单独使用 | 列表 | `account_list_accounts ...` 直接返回列表 |
| 过滤组合 + 单条详情意图 | 详情 | `account_list_accounts ...` → 若返回唯一 1 条且用户原文含"详情" → **二次** `account_get_account account_id=<n>`；否则保持列表 |
| 同时给了 id/code + 过滤条件 | — | 优先 id/code 单次 get；`ℹ️` 标注「已忽略过滤条件」 |

**核心约束**：`account_get_account` 只认 `account_id` / `code`，不接受 `name` / `uid` / 其它过滤——任何非 id/code 的输入要拿到「详情」结果必须走 2-step。

### Step 1 — 执行调用（按 Step 0 选定的路径）

#### 路径 A — 直接 get（id / code 输入）

```jsonc
// 工具 middle__account_get_account
{ "account_id": <n> }
// 或
{ "code": "<str>" }
```

#### 路径 B — 直接 list（过滤组合或 uid 列表意图）

```jsonc
// 工具 middle__account_list_accounts
{ "status": "<str>", "account_type": <1|2|3>, "market_id": <int>,
  "enable_status": <0|1|2|3>, "uid": "<str>", "limit": <int> }
// 仅传需要的字段，省略其余 key（不要传 "key": null 或 "key": ""）
```

#### 路径 C — 2-step (name → id → get)

```jsonc
// Step 1.C.1：name 解析（借 balance 接口拿 account_id）
// 工具 middle__balance_get_account_balance
{ "name": "<str>" }
// 提取返回里的 account_id

// Step 1.C.2：详情查询 —— 工具 middle__account_get_account
{ "account_id": <resolved_id> }
```

balance 返回多条命中（多账户同名，罕见）→ 列候选让用户选；零命中 → 报错「未找到账户名包含 `<name>` 的账户」。

#### 路径 D — 2-step (uid → id → get)

```jsonc
// Step 1.D.1：uid 列表查询 —— 工具 middle__account_list_accounts
{ "uid": "<str>" }
// 检查返回 results 长度

// Step 1.D.2：详情查询（仅在唯一命中时）—— 工具 middle__account_get_account
{ "account_id": <picked_id> }
```

- 唯一命中 → 自动二次 get，输出 detail 视图
- 多条命中（同 uid 对应多个 market 的账户，常见）→ 列候选表 `| ID | 平台 | 编码 | 名称 |`，让用户回复 "查账户 1204" 或 "查 Binance 那个" 等
- 零命中 → 报错「UID `<uid>` 不存在于中台」

#### 路径 E — 列表 + 单条详情自动升级

```jsonc
// Step 1.E.1：先 list —— 工具 middle__account_list_accounts
{ "<filter1>": <v1>, "<filter2>": <v2> }

// 当 user 原文含"详情" / "信息" / "info" 且 results 长度 == 1：
// 工具 middle__account_get_account
{ "account_id": <results[0].id> }
```

只把**有值的**过滤字段传上去，不要传空串。

### Step 2 — 字段映射（中文化展示）

中台返回字段以中台 OpenAPI 为准（运行时由 middle-mcp 暴露 schema）。常见字段映射：

| 展示列 | 字段名 | 备注 |
|--------|--------|------|
| 账户 ID | `id` 或 `account_id` | |
| 账户编码 | `code` | |
| 账户名称 | `name` | |
| 平台 | `market` 或 `market_id` | 数字 ID → 用 §Market ID 映射反查名称 |
| 账户类型 | `account_type` | `1` 普通 / `2` 子账户 / `3` 母账户 |
| 启用状态 | `enable_status` | `1` 启用 / `2` 停用（int） |
| 业务状态 | `status` | 字典见后端 `assets_account_status` |
| UID | `uid` | 交易所侧 UID |

字段缺失（key 不存在或值为 `null`）→ 单元格留空，不写 `null` / `undefined` / `0` 占位。

### Step 3 — 渲染输出

**列表模式（`account_list_accounts`）**：固定 Markdown 表格，列顺序：

```
| 账户 ID | 账户编码 | 账户名称 | 平台 | 账户类型 | 启用状态 | 业务状态 | UID |
|---------|---------|---------|------|---------|---------|---------|-----|
```

末尾追加总览：`共 N 条（limit=<N>）`。若返回条数等于 `limit`，提示「可能存在更多结果，请增大 `limit` 重试」。

**详情模式（`account_get_account`）**：Markdown 键值表，逐字段中文化展示：

```
| 字段 | 值 |
|------|----|
| 账户 ID | 1204 |
| 账户编码 | Mss0009 |
| 账户名称 | alpha-bn-spot |
| 平台 | Binance (id=4) |
| 账户类型 | 母账户 |
| 启用状态 | 启用 |
| ...（其它字段按返回展开） |
```

### Step 4 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `account_get_account` 既没传 `account_id` 也没传 `code` | 直接报错追问：「请提供账户 ID 或账户编码二选一」 |
| `account_get_account` 同时传两个 | 优先用 `account_id`，并在尾部 `ℹ️` 标注「已忽略 `code`，按 `account_id` 查询」 |
| 工具返回含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| 工具返回含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| 工具返回含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| 工具返回含 `timeout` / `connection refused` | 重试 1 次；仍失败 → `{status:"error", reason:"upstream_timeout"}` |
| 列表返回为空 | 不报错，直接回复「未查到符合条件的账户（过滤条件：...）」 |
| 详情返回 `404` / `not found` | 直接回复「账户 `<id|code>` 不存在或无权限访问」 |
| 其它错误 | 透传错误信息 → `{status:"error", reason:"upstream_error", upstream_message:<msg>}` |

## 输出示例

**列表**：

```
| 账户 ID | 账户编码 | 账户名称        | 平台    | 账户类型 | 启用状态 | 业务状态 | UID       |
|---------|---------|----------------|---------|---------|---------|---------|-----------|
| 1204    | Mss0009 | alpha-bn-spot  | Binance | 母账户  | 启用    | 1       | 12345678  |
| 1205    | Mss0010 | alpha-okx-uta  | OKX     | 母账户  | 启用    | 1       | 87654321  |

共 12 条（limit=50）
```

**详情**：

```
| 字段 | 值 |
|------|----|
| 账户 ID | 1204 |
| 账户编码 | Mss0009 |
| 账户名称 | alpha-bn-spot |
| 平台 | Binance (id=4) |
| 账户类型 | 母账户 |
| 启用状态 | 启用 |
| 业务状态 | 1 |
| UID | 12345678 |
```

**空结果**：

```
未查到符合条件的账户（过滤条件：account_type=3, market_id=4, enable_status=1）。
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `account_list_accounts` | 账户列表（多条件筛选） |
| `account_get_account` | 单账户详情（account_id / code 二选一） |

> 工具命名详情、参数清单、字段映射见 `common-middle-system-query/references/common-tool-naming.md` §2.2。

## 不做（边界）

- 不做账户资产 / 余额查询 → `common-middle-account-assets`
- 不做动账流水 / 历史明细 → `bs-transaction-history`
- 不做 CEX 费率/估值/VIP 等级（`value` / `vip_level` 字段在另一张表）→ `bs-exchange-rate`
- 不做账户级跨域聚合分析（应交给监控类 skill）
- 不创建 / 修改 / 删除任何账户（只读 GET）
- 不做账户名 → ID 自动映射（中台无此字典工具）

## 本 skill 文件结构

```
skills/common-middle-accounts/
├── SKILL.md           # 本文件
└── SKILL.tests.yaml   # trigger / non-trigger / DoD 测试
```

> MCP 调用约定收敛在 hub `common-middle-system-query`（`middle__<tool_name>` 直接调用），本 skill 不复述。
