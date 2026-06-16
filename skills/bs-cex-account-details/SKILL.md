---
name: bs-cex-account-details
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  CEX 单账户详情查询三连（middle-mcp `cex_get_account_trade_fee` /
  `cex_get_account_withdraw_limit` / `cex_get_account_borrow_info`）。
  按 account_id 查询某 CEX 母账户的「交易费率」/「提币额度」/「借贷信息」
  三类详情，覆盖 Binance / OKX / Bitget / Gate / Bybit / Deribit。
  返回 PageView 结构（tables[]），跨交易所字段差异巨大，必须按返回的
  columns 元数据解读。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: BS Team
  version: 1.0.0
complexity: L2
---

# CEX 单账户详情查询（Account Details Drill-down）

> NOTE (fleetent): 本 skill 的三个数据源工具（`cex_get_account_trade_fee` /
> `cex_get_account_withdraw_limit` / `cex_get_account_borrow_info`）以及上游 hub
> `common-middle-system-query` 均依赖中台 **middle-mcp**（`middle-mcp-server`）。
> my-bot 当前 9 个 MCP 面（armada / knowledge-bridge / email / google-drive /
> google-workspace / jira / confluence / bitbucket / playwright）**无 middle-mcp**。
> 已完整保留原业务逻辑（路由、PageView 解析、跨交易所字段差异、错误处理）；
> 接入 middle-mcp 后即可启用。当前请告知用户：CEX 账户详情查询暂未接入，需联系
> 中台 MCP 接入或对应 agent。下文凡 `middle-call.sh` / middle-mcp 工具调用均为
> 接入后路径，未接入时不可执行。

> ⛔ **执行前强制约束**（hub `common-middle-system-query` §共通强制约束的子集）
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由中台 MCP server（env 注入）处理，skill 不碰 token。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **严禁绕过 wrapper**：所有中台 MCP 调用必须通过 `$SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh`，**使用 `--args` JSON 模式**（见 hub `wrapper-caveats.md` §1）。
> 5. **数值精度零加工**：费率 / 利率 / 限额值原字面输出，禁止 `round()` / `float()` / 千分位转换（Deribit `feeType=relative` 后端已转为百分比展示，按字面输出即可）。
> 6. **字段严格按 columns 元数据解读**：不同 market 返回的 tables[] 结构差异巨大，**严禁**硬编码字段路径，必须按 `table.columns[].label/prop` 动态映射展示。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "查账户 1204 的交易费率" / "Binance 母账户 1204 现货手续费多少"
  - "OKX 账户 1230 的提币额度" / "可提多少 USDT"
  - "Bybit 账户 1240 的借贷信息" / "在借订单 / 借币利率"
- **被其它 skill 调用**：风控 / 监控类 skill 在做账户级合规审计时需要拉详情。

## 能力边界

| 用户意图 | 用本 skill | 工具 | 改用 |
|---------|----------|------|------|
| 单账户**交易费率**明细（VIP 等级 / symbol） | ✅ | `cex_get_account_trade_fee` | — |
| 单账户**提币额度**明细（链路 / 单次 / 24h 限额 / 手续费） | ✅ | `cex_get_account_withdraw_limit` | — |
| 单账户**借贷信息**（可借币种 / 在借订单 / 杠杆 / 历史利率） | ✅ | `cex_get_account_borrow_info` | — |
| **列出**所有 CEX 母账户（含 USD 估值 / VIP）| ❌ | — | `bs-exchange-rate` |
| 账户当前持仓 / 余额 | ❌ | — | `common-middle-account-assets` |
| 账户主数据（不含费率细节）| ❌ | — | `common-middle-accounts` |
| 动账流水 | ❌ | — | `bs-transaction-history` |
| 法币汇率 | ❌ | — | `bs-fiat-exchange-rate` |

## 前置依赖：必须先有 `account_id`

三个工具都**必须**传 `account_id`，且必须是 CEX 母账户（来自 `cex_list_exchange_rate_accounts` 的 `id`）。如果用户只给了账户编码 / 名称 / UID：

1. **先调** `bs-exchange-rate`（即 `cex_list_exchange_rate_accounts`）按 `code` / `name` / `uid` 找到对应 `id`
2. **再调** 本 skill 的对应工具传 `account_id=<id>`
3. 中间 ID 解析结果可缓存复用，避免每次详情查询都重新列表

## 调用模式

所有中台 MCP 调用必须通过 hub wrapper（接入 middle-mcp 后用内置 `bash_exec` 跑该脚本）：

```bash
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
     <tool_name> '<args_json>'
```

**示例**（`bash_exec`）：

```bash
# 1) 查账户 1204 交易费率
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  cex_get_account_trade_fee '{"account_id": 1204}'

# 2) 查账户 1230 提币额度
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  cex_get_account_withdraw_limit '{"account_id": 1230}'

# 3) 查账户 1240 借贷信息（强制刷新缓存）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  cex_get_account_borrow_info '{"account_id": 1240, "refresh": true}'
```

## 输入参数（三个工具签名相同）

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `account_id` | int | **是** | — | CEX 母账户主键 ID（来自 `cex_list_exchange_rate_accounts.id`） |
| `refresh` | bool | 否 | `false` | 是否强制刷新缓存。`false`=走缓存（默认每小时刷新），`true`=立即重拉 |

> ⚠️ `refresh=true` 在 `cex_get_account_borrow_info` 工具上前端已禁用按钮，**是否生效以后端为准**——agent 调用不会报错，但实际行为可能仍然是缓存数据。

> ⚠️ **OKX / Bybit 的 borrow_info 有「采集中」机制**：杠杆数据超过 30 分钟未采集会异步触发后台采集，此时返回的 tables[] 含 `title` 带「采集中」字样的空表，需稍后重试。本 skill 自动识别后在输出尾部 `ℹ️` 标注「`<market>` 杠杆数据采集中，请稍后重试」。

## 工作流程

### Step 0 — 路由判断（trade_fee / withdraw_limit / borrow_info）

按用户意图关键词路由：

- 「费率」「手续费」「VIP 等级费率」「现货费率」「合约费率」→ `cex_get_account_trade_fee`
- 「提币额度」「提币限额」「最大提币」「24h 可提」「提币手续费」→ `cex_get_account_withdraw_limit`
- 「借贷」「借币」「在借订单」「可借」「利率」「保证金」→ `cex_get_account_borrow_info`
- 用户问"账户详情"模糊 → 串行调用三个，并 `ℹ️` 标注「已合并展示三类详情」

### Step 1 — 确认 `account_id`

- 用户直接给 `account_id`（纯数字 + 账户上下文）→ 直接进 Step 2
- 用户给 `code` / `name` / `uid` → 先调 `bs-exchange-rate` 解析 `id`；命中唯一 → 进 Step 2；命中多条 → 列候选让用户选；零命中 → 报错「未找到 CEX 母账户 `<X>`」

### Step 2 — 调用主接口

```bash
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  <tool_name> '{"account_id": <n>, "refresh": <true|false>}'
```

### Step 3 — 解析 PageView 结构

返回固定结构（三个工具一致）：

```json
{
  "title": "...",
  "desc": "...",
  "updated_at": "...",
  "tables": [
    {
      "title": "...",
      "desc": "...",
      "links": [...],
      "table": {
        "columns": [{"label": "中文标签", "prop": "字段名"}, ...],
        "data": [{...row}, ...],
        "filters": {...}
      }
    },
    ...
  ]
}
```

⚠️ **每个 table 的 columns 才是字段含义的权威来源**，严禁硬编码字段名解读 data。具体到不同 market 的表格差异，详见各工具内置 docstring（在 `references/common-tool-naming.md` §2.5 已概要列出）：

| Market | trade_fee 表数 | trade_fee 维度 | withdraw_limit 列差异 | borrow_info 维度 |
|--------|---------------|---------------|---------------------|------------------|
| Binance (4) | 2 | VIP 等级 | 标准列 | VIP 可借币种 + 在借订单 |
| OKX (10) | 2 | 手续费分组 | 24h 可提(USD) 关键 | 杠杆可借（母/子）+ 活期借币 |
| Bybit (19) | 2 | 交易对 symbol（默认含 BTCUSDT 等 5 对） | 标准列 | 借贷信息（母/子） |
| Bitget (42) | 2~3 | VIP 等级（含合约 30 天交易量、24h 提币）| 含「是否可充」「是否需 Tag」 | 可借 + 可质押 + 借款订单 |
| Gate (43) | 3 | BTC/ETH 双币种 | 仅 BTC/ETH/USDT/USDC 4 种 | 总借贷量 + 借币限额 + 历史利率 |
| Deribit (44) | N | instrument_type 品类 | 含「网络费」「最小确认数」「跨抵押池」 | 保证金概览（**当前后端 summaries=False 写死，返回空数据**） |

### Step 4 — 渲染输出

每个 table 单独渲染：

1. 标题：用 `tables[i].title`（如返回为空则用工具名 + market 名拼装）
2. 表头：按 `columns[].label` 中文展示
3. 数据：按 `columns[].prop` 取 `data[i][prop]`，**原字面**展示
4. 字段缺失 → 单元格留空，不写 `null` / `undefined` / `0` 占位

末尾汇总：`数据更新时间：<updated_at>`（UTC → UTC+8）+ 缓存说明 `（缓存数据，每小时刷新一次。如需最新加 refresh=true 参数）`

### Step 5 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `account_id` 缺失或非整数 | 追问：「请提供 CEX 母账户的 account_id（纯数字主键，可从 bs-exchange-rate 列表查）」|
| `account_id` 不存在 / 非 CEX 母账户 | 回复「账户 `<id>` 不存在或不是 CEX 母账户。本 skill 仅覆盖 Binance/OKX/Bitget/Gate/Bybit/Deribit 母账户。」|
| 返回 `tables` 为空数组 | 回复「账户 `<id>` 暂无 `<工具中文名>` 数据。可能原因：账户未配置 / Deribit summaries 后端禁用 / 数据采集中。」|
| 表格 `title` 含「采集中」 | 输出尾部 `ℹ️` 标注「`<market>` 数据采集中，请稍后重试」|
| stderr 含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| stderr 含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| stderr 含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| stderr 含 `timeout` / `connection refused` | 重试 1 次（底层交易所限频可能慢） |
| 其它非 0 退出 | 透传 stderr |

## 输出示例

```
账户 1204（alpha-bn-spot @ Binance, VIP 等级 7）交易费率：

### 表 1：VIP 流动性概览
| 字段1 | 字段2 | ... |  (按 columns 元数据展示)

### 表 2：各 VIP 等级现货&杠杆费率
| VIP 等级 | 现货 Maker | 现货 Taker | ... |  (同上)

数据更新时间：2026-05-29 14:32:15 UTC+8
（缓存数据，每小时刷新一次。如需最新加 refresh=true 参数）
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `cex_get_account_trade_fee` | 交易费率明细 |
| `cex_get_account_withdraw_limit` | 提币额度明细 |
| `cex_get_account_borrow_info` | 借贷相关信息 |

> 三个工具的返回结构与跨平台差异概要见 `common-middle-system-query/references/common-tool-naming.md` §2.5。

## 不做（边界）

- 不做 CEX 母账户列表查询 → `bs-exchange-rate`
- 不做账户资产 / 余额 → `common-middle-account-assets`
- 不做账户主数据 → `common-middle-accounts`
- 不做动账流水 → `bs-transaction-history`
- 不做实时交易所行情 → 行情类 skill
- 不创建 / 修改 / 设置费率（只读 GET）
- **不硬编码跨平台字段差异**——所有字段含义来源于返回的 `table.columns`

## 本 skill 文件结构

```
skills/bs-cex-account-details/
├── SKILL.md
└── SKILL.tests.yaml
```

> wrapper 收敛在 `common-middle-system-query/scripts/middle-call.sh`，工具清单见 `common-middle-system-query/references/common-tool-naming.md` §2.5。
