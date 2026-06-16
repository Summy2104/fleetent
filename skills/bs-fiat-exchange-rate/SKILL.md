---
name: bs-fiat-exchange-rate
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  法币历史汇率报告生成（middle-mcp `exchange_rate_get_exchange_rate_report`）。
  按源币种（base，ISO 4217 如 SGD/USD/EUR）+ 目标币种（quote，如 HKD/CNY/JPY）
  + 时间范围（起止年月），生成包含每日汇率明细 + 整体平均 + 每月平均的
  Excel 文件。仅当上游 hub 路由进入本 skill 时生效。
  注意：本 skill 依赖中台 middle-mcp，fleetent/my-bot 当前 9 个 MCP 面无对应（见正文 NOTE）。
status: active
metadata:
  author: BS Team
  version: 1.0.0
complexity: L1
---

# 法币历史汇率报告（Fiat Exchange Rate Report）

> NOTE (fleetent): 此处依赖中台 middle-mcp（`exchange_rate_get_exchange_rate_report` 工具），my-bot 当前 9 个 MCP 面无对应。
> 已保留原逻辑描述（参数解析 / 时间范围兜底 / 返回解析 / 文件交付 / 错误处理）；接入 middle-mcp（注册为 fleetent MCP server，工具名将变为 `{server_id}__exchange_rate_get_exchange_rate_report`）后即可启用。
> 当前请告知用户：法币历史汇率报告需要中台 middle-mcp，本部署暂未接入，请联系对应中台 agent 或运维。

> ⛔ **执行前强制约束**
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 MCP server 的 env 注入，skill 不碰 token。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **数值精度零加工**：汇率值原字面输出，禁止 `round()` / `float()` / 千分位转换。
> 5. **文件交付**：xlsx 用内置 `send_file` 投递回当前对话（频道→频道 / 私信→私信），聊天只输出摘要，严禁向用户透露内部文件路径。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "拉一份 SGD 兑 HKD 2025 年的汇率报告"
  - "USD/CNY 全年汇率，按月平均"
  - "EUR/JPY 2025 Q1 法币汇率"
- **被其它 skill 调用**：财务对账 / 估值换算类 skill 需要法币汇率历史快照作为输入。

## 能力边界

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 法币 → 法币历史汇率（按月范围导 xlsx） | ✅ | — |
| 实时法币汇率（如"现在 USD 兑 CNY 多少"） | ⚠️ 工具是历史报告，不是实时；如需当下值用本月范围调用，自行从结果末日取最新值 | — |
| 数字货币汇率 / 估值（如 USDT 在 Binance）| ❌ | `bs-exchange-rate`（CEX 母账户费率管理）|
| 实时币价 | ❌ | `common-ns-monitor` / 行情类 skill |
| 账户资产 / 余额 / 流水 | ❌ | `common-middle-*` 系列对应 spoke |

## 调用模式

> NOTE (fleetent): 原 OpenClaw/Hermes 经 hub wrapper `middle-call.sh` + `mcpfast` 调中台。fleetent 里 MCP 调用由 agent loop 直接发起（工具名 `{server_id}__<tool>` 双下划线），鉴权由 MCP server 的 env 注入。下文 `middle__exchange_rate_get_exchange_rate_report` 是占位工具名——middle-mcp 接入并注册为 fleetent MCP server 后，`middle__` 即对应其 server_id。**当前 my-bot 未接入 middle-mcp，本调用无法执行**，请按本文件顶部 NOTE 告知用户。

中台接入后，由 agent loop 直接发起 MCP 工具调用（参数即下方 JSON）：

```text
# 1) SGD 兑 HKD 2025 年 1-3 月
tool: middle__exchange_rate_get_exchange_rate_report
args: {"base": "SGD", "quote": "HKD",
       "start_year": 2025, "start_month": 1,
       "end_year": 2025, "end_month": 3}

# 2) USD 兑 CNY 全年（默认 1-12 月）
tool: middle__exchange_rate_get_exchange_rate_report
args: {"base": "USD", "quote": "CNY", "start_year": 2025}

# 3) EUR 兑 JPY 单月（如 2025 年 6 月）
tool: middle__exchange_rate_get_exchange_rate_report
args: {"base": "EUR", "quote": "JPY",
       "start_year": 2025, "start_month": 6,
       "end_year": 2025, "end_month": 6}
```

## 输入参数

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| `base` | string | **是** | — | 源币种 ISO 4217 代码（大写，如 `SGD` / `USD` / `EUR`） |
| `quote` | string | **是** | — | 目标币种 ISO 4217 代码（大写，如 `HKD` / `CNY` / `JPY`） |
| `start_year` | int | 否 | 当前年 | 起始年份，如 `2025` |
| `start_month` | int | 否 | `1` | 起始月份 1–12 |
| `end_year` | int | 否 | 同 `start_year` | 结束年份 |
| `end_month` | int | 否 | `12` | 结束月份 1–12 |

## 用户输入解析

- 用户给「`A/B`」「`A 兑 B`」「`A 到 B`」（A、B 均为 ISO 4217 大写代码）→ `base=A` / `quote=B`
- 用户给「YYYY 年 M 月到 YYYY 年 N 月」→ `start_year` / `start_month` / `end_year` / `end_month`
- 用户给「YYYY 年全年」/「YYYY 年」→ `start_year=YYYY`（其它字段默认）
- 用户给「Q1」「Q2」「Q3」「Q4」→ 转 `start_month` / `end_month` 对应 1-3 / 4-6 / 7-9 / 10-12
- 用户给「最近 N 个月」「过去 N 月」→ 当前年月起回推 N 个月得到 `start_*` / `end_*`
- `base` 或 `quote` 缺失（无法识别 ISO 代码）→ 追问用户：「请提供源币种和目标币种的 ISO 4217 代码（如 `SGD/HKD`）」
- 用户只给币种对、不给时间 → 默认拉本年全年（`start_year=当前年, start_month=1, end_month=12`），并在尾部 `ℹ️` 标注「默认时间范围：本年全年」

## 工作流程

### Step 0 — 解析必填字段

`base` + `quote` **必填**，缺一即追问，不调脚本。其它字段按 §用户输入解析 兜底。

### Step 1 — 调用主接口

由 agent loop 发起 MCP 工具调用（中台接入后 `middle__` 对应 middle-mcp server_id）：

```text
tool: middle__exchange_rate_get_exchange_rate_report
args: {"base": "<str>", "quote": "<str>",
       "start_year": <int?>, "start_month": <int?>,
       "end_year": <int?>, "end_month": <int?>}
```

### Step 2 — 解析返回 + 交付文件

工具返回包含生成的 xlsx 文件引用。具体返回结构（文件路径 / base64 / 直接二进制）以中台实际行为为准；首次调用时按以下顺序兜底：

1. 顶层若有 `file_url` / `file_path` / `download_url` → 取作文件位置
2. 顶层若有 `data` + `filename` 字段（base64）→ 用 `run_code` 解码后 `write_file` 到 workspace `outbound/fiat-exchange-rate/{YYYY-MM}/fiat_<base>_<quote>_<range>.xlsx`
3. 文本含 `已生成 Excel 文件：<path>` → 提取路径

文件位置确定后，用内置 `send_file` 投递给用户（投递回当前对话：频道→频道 / 私信→私信），文件名形如 `fiat_<base>_<quote>_<start>-<end>.xlsx`。聊天只输出摘要，不暴露内部文件路径。

### Step 3 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `base` / `quote` 缺失或非 ISO 4217 大写代码 | 追问：「请提供源币种与目标币种 ISO 4217 代码（如 `USD/CNY`）」|
| `start_month` / `end_month` 不在 1-12 | 追问纠正 |
| `end_year/month` 早于 `start_year/month` | 追问纠正 |
| stderr 含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| stderr 含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| stderr 含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| stderr 含 `timeout` / `connection refused` | 重试 1 次（汇率报告生成可能较慢，加重试缓冲） |
| 返回结构无法解析 | `{status:"error", reason:"unexpected_response_shape", sample:<前 200 字符>}` |
| 中台返回"币种对不存在" / "无数据" | 「未查到 `<base>/<quote>` 在 `<start>~<end>` 区间的汇率数据。请确认币种代码或时间范围。」|

## 输出示例

```
法币汇率报告已生成：
- 币种对：SGD/HKD
- 时间范围：2025-01 ~ 2025-03
- 内容：每日汇率明细 + 整体平均 + 每月平均
- 文件：已通过 send_file 投递到当前对话（fiat_SGD_HKD_2025-01_2025-03.xlsx）
```

空结果时：

```
未查到 SGD/XYZ 在 2025-01 ~ 2025-03 区间的汇率数据。请确认目标币种 ISO 代码（如 HKD / CNY / JPY）是否正确。
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `exchange_rate_get_exchange_rate_report` | 主接口，生成 xlsx 报告 |

> 工具命名详情、参数清单见 `common-middle-system-query/references/common-tool-naming.md` §2.4。

## 不做（边界）

- 不做数字货币汇率 / 估值（→ `bs-exchange-rate`）
- 不做实时币价 / 行情（→ `common-ns-monitor`）
- 不做 USD→CNY 等单点换算（用户应自己从 xlsx 末日取值）
- 不做账户级估值换算
- 不创建 / 修改任何记录（只读 GET）

## 本 skill 文件结构

```
skills/bs-fiat-exchange-rate/
├── SKILL.md
└── SKILL.tests.yaml
```

> NOTE (fleetent): 原 hub wrapper（`common-middle-system-query/scripts/middle-call.sh`）是 OpenClaw/Hermes 的 mcpfast 入口；fleetent 不需要 wrapper，MCP 调用由 agent loop 直接发起（`middle__<tool>`）。中台 middle-mcp 接入前本 skill 不可执行。
