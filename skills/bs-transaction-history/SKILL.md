---
name: bs-transaction-history
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台账户动账流水查询（middle-mcp `transaction_list_account_transactions` V2）。
  **必填账户上下文**（`account_id` 或 `account_code` 二选一，后端防全表扫描）
  + 时间范围拉取资金进出明细，输出 15 列固定布局 xlsx + 一行摘要。
  **Do NOT use for**: 按 TxID 查到账状态（本工具 `tx_id` 字段必须配合
  account_id/account_code，做不了纯 TxID 全局反查；TxID 到账查询请走 NS 侧
  `common-ns-flows.r_transactions`，它的 `txid` 字段支持无账户上下文反查）；
  纯账户名/UID 查账户主数据（→ common-middle-accounts）；账户资产快照
  （→ common-middle-account-assets）。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: BS Team
  version: 0.2.0
complexity: L1
---

# 中台动账流水查询

> NOTE (fleetent): 本 skill 的数据源是 **中台 `middle` MCP**
> （`transaction_list_account_transactions` / `balance_get_account_balance`）。
> 中台 `middle` MCP server **不在 my-bot 已挂载的 9 个 MCP 面内**（见适配指南 §2），
> my-bot 当前无对应能力。**渲染 xlsx 的 `render_xlsx.py` 已完整移植、纯本地可跑**；
> 仅「取动账流水数据」这一步缺 MCP 桥接。接入中台桥接 / `middle__<tool>` 能力后，
> 按下文「取数 → 渲染」两步即可启用。当前缺数据时请告知用户「中台流水查询能力
> 待接入」，或经 common-middle-system-query hub 路由（hub 接入桥接后透传）。
> market 平台名映射走 NS armada（`armada__armada_get`，已可用，见「依赖」段）。

> ⛔ **执行前强制约束**
> 1. 严禁 `curl` 中台 HTTP 端点；鉴权由 MCP server env 注入（接入桥接后），skill 不碰 token。
> 2. 严禁输出 Authorization / Bearer / X-API-Key 任何片段。
> 3. 数值精度零加工：金额 / 余额原字面写入，禁止 `round` / `float()` / 千分位 / `f"{x:.Nf}"`。脚本内部用 `parse_float=str` 锁字面，agent 这边不需要再处理数字。
> 4. **绝不**把整份动账流水 JSON 贴进聊天上下文。agent 取数后落临时 JSON 文件，用 `--input` 喂给脚本渲染；聊天只输出一行摘要 + 文件投递。
> 5. **输出 xlsx 必须正好 15 列**（脚本写死的标准布局）：① 流水ID ② 账户名称 ③ 账户代码 ④ 币种 ⑤ 金额 ⑥ 余额(变动后) ⑦ 流向 ⑧ 出入账时间(UTC+0) ⑨ 平台 ⑩ 描述 ⑪ 关联NS流水 ⑫ 来源地址 ⑬ 目标地址 ⑭ TxID ⑮ 更新时间。agent 不要尝试增删列、不要要求脚本输出别的列。需要新增列请改 `scripts/render_xlsx.py:COLUMNS`，不要让 agent 自行拼。
> 6. **脚本 stdout JSON 里只要包含 `file` 字段，agent 必须用内置 `send_file` 把文件投递给用户，rows=0 也不例外**。空区间脚本会生成只有表头的 .xlsx —— **不允许** 只用文字"区间内无动账流水"打发用户、把文件吞掉。正确做法：先回一行摘要「区间内无动账流水（<标识>=<值>, 时间 <start> ~ <end>）」，再 `send_file` 投递空表头文件。

## 调用（取数 → 渲染 → 投递，三步）

### Step 1 — 取动账流水数据（中台 middle MCP）

> NOTE (fleetent): 此步依赖中台 `middle` MCP，my-bot 当前 9 个 MCP 面无对应。
> 桥接接入后，agent 直接调用工具 `middle__transaction_list_account_transactions`
> （兜底 `middle__transaction_get_account_transactions`），参数：
>
> ```
> account_id=<N>   或   account_code=<STR>     # 二选一，互斥（V2 主接口拒收 account_name）
> tx_start_time="2026-04-29 00:00:00"          # UTC+0
> tx_end_time="2026-05-19 23:59:59"            # UTC+0
> ordering="-date"
> page_size=200                                 # 服务端最多 200
> ```
>
> 用户给的是**账户名称**（邮箱形态 / `alpha-mss-0009`）时，V2 主接口拒收 name，
> 须先调 `middle__balance_get_account_balance`（参数名 **`name=`**）把 name 解析成
> `account_id`，再用 `account_id` 查流水。多账户命中时列候选让用户挑（见错误处理）。
>
> 拿到流水 JSON 后，用 `write_file` 落到临时文件（如 `outbound/动账流水/_raw_tx.json`），
> **不要**把整份 JSON 贴进聊天。

### Step 2 — （可选）取 market 平台名映射（NS armada，已可用）

`render_xlsx.py` 的「平台」列要把 `market` id 翻成平台名。优先用 NS armada 实时映射，
经 **唯一合法入口** ns-call wrapper 注入鉴权后由 agent 发起 `armada__armada_get`：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/digital_coin/category"
```

wrapper 打印一行 `ARMADA_CALL armada__armada_get path=/v1/accounts/digital_coin/category _meta={...}`，
agent 据此发起 `armada__armada_get` 工具调用拿 JSON，用 `write_file` 落到
`outbound/动账流水/_market_map.json`，传给 Step 3 的 `--market-map-input`。
（`$UID` 替换为本次请求的 sender_id；缺映射不阻塞，脚本回落静态 `scripts/market_id_map.json`，
未命中 id 显示 `market#<id>`。）

### Step 3 — 渲染 xlsx（run_code，纯本地 openpyxl，已预装）

```bash
python3 $SKILLS_DIR/bs-transaction-history/scripts/render_xlsx.py \
  --account-id 1204 \
  --tx-start-time '2026-04-29 00:00:00' \
  --tx-end-time   '2026-05-19 23:59:59' \
  --input outbound/动账流水/_raw_tx.json \
  [--market-map-input outbound/动账流水/_market_map.json] \
  --output 'outbound/动账流水/2026-05/middle_transactions_1204_20260429_20260519.xlsx'
```

- 标识三选一（`--account-id` / `--account-code` / `--account-name`），**仅用于文件名 / 摘要**；
  实际取数已在 Step 1 完成。用账户名查询时这里传 `--account-name`（脚本不再调任何接口）。
- 输出落 workspace `outbound/动账流水/{YYYY-MM}/*.xlsx`（关键词目录 + 月份分桶）。
- stdout 永远一行 JSON 状态：

```json
{"status":"ok","file":"<path>","rows":N,"identifier":"<X>"}
```

错误时 stderr 一行 JSON + 非零退出码。reason 码：`missing_account_identifier` /
`multiple_account_identifiers` / `input_file_unreadable` / `invalid_json`。
退出码：`0` 成功 / `2` 用法错误 / `3` JSON 解析失败 / 结构未知。

### Step 4 — 投递

用内置 `send_file` 把 `file` 字段指向的 .xlsx 投递回当前对话（频道→频道 / 私信→私信），
配一行摘要：`共拉取到 N 条流水（<标识>=<值>, 时间 <start> ~ <end>）`。**不要**贴流水 Markdown 表格，
**不要**暴露内部文件路径。

## 输入参数解析

| 用户原话 | 标识 / 接口字段 | 备注 |
|---|---|---|
| 邮箱形态字符串 / 账户名（`bntrad8@nsdigital.io` / `alpha-mss-0009`） | 先 balance 解析成 `account_id` | 子串匹配，可能跨多个账户 |
| 数字 id（`account_id=1204` / `账户 1204`） | `account_id` | 最精确 |
| 账户编码（`Mss0009` 等） | `account_code` | 与 id 等价 |
| 时间范围（`4/29-5/19` / `上周` / `最近 7 天`） | `tx_start_time` / `tx_end_time` | 补 `YYYY-MM-DD 00:00:00` / `23:59:59`，**UTC+0**（V2 接口的 `date` 字段也是 UTC+0，不做时区转换）|
| `top N` / `前 N` | `page_size min(N,200)` | 服务端最多 200 条 |

时间范围**必填**，没给就停下来追问（追问模板：「请提供查询时间范围，格式 `YYYY-MM-DD`，我再拉取流水」），**不补默认**。账户标识同理。

## 工作流

1. **Step 0 — 解析参数**。任意必填字段缺失 → 追问，不取数。
2. **Step 1 — 取数**（中台 middle MCP，见上面 NOTE）。用账户名时先 balance 解析。落 JSON 文件，不贴聊天。
3. **Step 2 — （可选）取 market 映射**（NS armada）。落 JSON 文件。
4. **Step 3 — 渲染**（`run_code` 跑 `render_xlsx.py --input`）。读 stdout 一行 JSON：
   - `status:"ok"` (`rows>0`) → Step 4 投递（`send_file` + 一行摘要）。
   - `status:"ok"` (`rows==0`) → **仍投递**（只有表头的 .xlsx），摘要：「区间内无动账流水（<标识>=<值>, 时间 <start> ~ <end>）」，再 `send_file`。⚠️ **不要**只回文字、把文件吞掉 —— 强约束 §6。
   - `status:"error"` → 按下文错误处理透传给用户。
5. **Step 4 — 投递**：内置 `send_file` 投递文件 + 一行摘要。**不要**贴流水 Markdown 表格。

## 错误处理

| 场景 | reason / 处理 |
|--------|------|
| 中台桥接未接入 | 告知用户「中台动账流水查询能力待接入」（见顶部 NOTE），不臆造数据 |
| 中台鉴权失败（接入后 401/403） | 透传上游报错，提示运维补 API Key |
| balance 接口零命中（账户名） | 让用户确认账户名称或直接给 account_id / account_code |
| balance 多账户命中（账户名） | 列出候选账户让用户挑，挑完用 `account_id` 重新取数 |
| `missing_account_identifier` / `multiple_account_identifiers` | 脚本侧用法错误（agent 本不该让它发生）—— 修正标识参数重跑 |
| `input_file_unreadable` / `invalid_json` | agent 落盘的 JSON 文件有问题 —— 重新取数 / 检查写文件这一步 |

## 性能诊断

`render_xlsx.py` 跑慢了加 `--timing`，stdout/stderr 的 JSON 末尾会多 `timing` 段
（`json_parse_ms` / `xlsx_build_ms` / `xlsx_save_ms` / `total_ms`）。纯本地渲染基线
`xlsx_build+save < 50ms` / `total_ms ≈ 0.5s`（不含 Python 冷启）。取数耗时不在脚本内
（已移到 agent 的 MCP 工具调用），不再有 `mcpfast_ms`。

## Replay / 离线渲染

`render_xlsx.py` 始终从 `--input` 读 JSON（纯本地、不触网）。要离线复现历史 payload，
把捕获的流水 JSON 落文件后照常 `--input` 即可；market 映射缺省回落静态表，
或显式给 `--market-map-input`。

## 不做（边界）

- 不做对账分析（交给 `bs-flow-resolving`）。
- 不做估值换算 / 账户级汇总。
- 不查 NS 或其它系统的流水（本 skill 只查中台；NS market 映射仅用于平台列翻译）。
- 不创建 / 修改任何记录（只读 GET）。
- 不贴流水 Markdown 表格 —— 只给 .xlsx 文件（`send_file` 投递）+ 一行摘要。

## 依赖

- 主接口（**待接入桥接**）：中台 `middle__transaction_list_account_transactions`（V2，兜底名
  `middle__transaction_get_account_transactions`），**强制**需要 `account_id` 或 `account_code`，
  不接受 `account_name`。中台 `middle` MCP 不在 my-bot 9 个 MCP 面内，见顶部 NOTE。
- 账户名解析（**待接入桥接**）：`middle__balance_get_account_balance`（参数名 `name=`），
  用账户名查询时先调它解析出 `account_id`。
- 平台名映射（主路径，**已可用**）：NS armada `armada__armada_get path=/v1/accounts/digital_coin/category`，
  返回 `{id, market}` 列表。经 `common-ns-system-query/scripts/ns-call.sh` wrapper 注入鉴权后由
  agent 发起；结果落 JSON 后用 `--market-map-input` 传给脚本。
- 平台名映射（兜底）：`scripts/market_id_map.json`，未给 `--market-map-input` 或 armada 调不通时使用。
  未命中任何映射的 id 显示为 `market#<id>`，不阻塞 xlsx 生成。
- 15 列布局、派生列（金额 / 流向 / 平台）、字段映射、数值精度处理细节：详见 `scripts/render_xlsx.py:COLUMNS`
  与同文件顶部 docstring。
