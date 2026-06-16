---
name: common-ns-flows
description: >
  NS 系统流水 / 对账 / FDL 结算 / 资金端流动性子域查询（armada MCP，22 个端点）。
  覆盖业务流水（biz_transactions，含表头）、逻辑流水（v_transactions / v_flows）、
  实际流水（r_transactions）、NS对账（reconciliation）、FDL 三步结算、
  资金端流动性看板（fund_dashboard）、项目资金来源（biz-fund-source-stat）。
  典型场景：按业务线 / 项目 / 流程维度查 NS 业务记账层流水，
  FDL 结算、资金端看板，或查项目本金 / 资金来源汇总。
  **按 TxID 查到账状态也走本 skill**：通过 `r_transactions.txid` 字段
  全局反查实际流水，**不需要账户 / 业务线上下文**——这是中台
  transaction_list_account_transactions 做不到的（中台 tx_id 字段必须
  配合 account_id/account_code），TxID 到账确认场景必须用 NS。
  触发词：业务流水、逻辑流水、实际流水、NS对账、FDL 结算、资金端流动性、项目本金、
  TxID 查到账、TXID 查询、tx hash 查询、链上哈希查询、单笔到账确认、到账状态、
  是否到账、这笔到账了吗、按 TxID 查、按 txid 查、按 TxnID 查、按 hash 查、
  资金到账查询、查到账。
  Do NOT use for：
  按账户标识+时间范围导 xlsx（→ bs-transaction-history）；
  账户资产快照 / 可用冻结余额（→ common-middle-account-assets）；
  业务资金汇总表 / 按项目汇总（→ common-ns-biz-fund-summary）；
  客户/项目/银行/数币账户/白名单查询（→ common-ns-masterdata）；
  流程实例/资金计划/审批详情（→ common-ns-process）；
  币价/调仓/交易所账户（→ common-ns-monitor）；
  跨域不确定回 `common-ns-system-query` 父 skill。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# NS 流水 / 对账 / FDL / 资金端流动性 查询

本 skill 是 `common-ns-system-query` 的子 skill，覆盖流水 + 对账 + FDL + 资金端流动性域（共 22 个端点）。输出规范、信任模型、降级开关、完整 wrapper 语义请回父 skill `SKILL.md`。

## Step 0 — 鉴权预检（必须先做，失败立即终止）

1. 调用内置 `whoami` 工具，从返回的「发起人 ID」字段取得 `sender_id`（fleetent 由 inbound 消息会话上下文注入，非用户可控）
2. 校验：`sender_id` 存在 + 匹配正则 `^U[A-Z0-9]{8,}$`
3. **任一校验失败** → 回复下列固定话术并终止（不得继续任何步骤）：

   > ❌ 此查询仅限 Slack 渠道使用。当前上下文无法识别 Slack 用户身份，已阻止 NS 系统查询。

4. 通过 → 把取得的 `sender_id` 作为本轮**每次** `ns-call.sh` 调用的首个位置参数传入（见 §调用模式）。**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`。
5. **每轮 turn 开头必重新执行 Step 0**（防跨 turn 污染）。

> **Subagent 透传协议**：父 agent 调用 `sub_agent` / `invoke_agent` 时，若子 agent 需使用本 skill，**必须**在 prompt 参数最前面原样插入一行 JSON：`{"sender_id": "<父 agent 本轮的 sender_id>"}`，正文从下一行开始。父未透传 → 子 agent `whoami` 无法取得发起人 → Step 0 被拒。

## 域内路由

| 用户表述 | 读哪个 reference |
|---------|------------------|
| 业务流水列表 / 业务流水明细 / 业务流水资金汇总 | `references/transactions-biz-headers.md` |
| 业务流水表头 / 表头关联行为 / 资金标签 | `references/transactions-biz-headers.md` |
| 查本金 / 项目本金 / 项目资金来源 / 实际资金来源 / 理论资金来源 | `references/biz-transactions-fund-source-stat.md` |
| 逻辑交易流水 / 逻辑账户流水 | `references/transactions-logical.md` |
| 逻辑账户流水看板 / 资产端概览 / 资金端概览 / 资金端本金 / 资金端资产分布 | `references/transactions-v-flows-dashboard.md` |
| 实际交易流水 / 动账 / 账户余额核对 | `references/transactions-real-reconciliation.md` |
| FDL 结算单 / FDL 客户 / FDL 结算详情 | `references/transactions-fdl.md` |
| 资金端流动性看板 / 流动性看板 / 流程流水（看板场景） | `references/fund-dashboard.md` |

## 端点索引（22 个）

### 业务流水 (11)

- `GET /v1/biz_transactions` — 业务流水列表（明细）
- `GET /v1/biz_transactions/stat` — 业务流水资金汇总
- `GET /v1/v_transactions` — 逻辑交易流水列表
- `GET /v1/v_flows` — 逻辑账户流水列表
- `GET /v1/v_flows/asset_side/overview` — 资产端概览（流入流出 + 业务线占用分布）
- `GET /v1/v_flows/fund_side/asset_distribution` — 资金端资产占用分布快照（截至某日期）
- `GET /v1/v_flows/fund_side/overview` — 资金端概览（资金池变动 + 业务线占用分析）
- `GET /v1/v_flows/fund_side/principal` — 资金端本金看板（币种维度）
- `GET /v1/process_transactions` — 流程流水列表（资金端流动性看板场景下用 fund_type 筛选）
- `GET /v1/process_transactions/summary` — 流程流水汇总（资金端流动性看板场景下用 fund_type 筛选）
- `GET /v1/r_transactions` — 实际交易流水列表

### 对账 (3)

- `GET /v1/reconciliation/adjustment/real_transactions/r_flows` — NS 动账流水
- `GET /v1/reconciliation/middle_account/transactions` — 中台侧动账流水
- `GET /v1/reconciliation/adjustment/account_balance` — 指定数币账户余额

### FDL 结算 (3)

- `GET /v1/fdl-settlements` — 结算单月份列表
- `GET /v1/fdl-settlements/{settlement_id}/customers` — 结算单客户列表
- `GET /v1/fdl-settlements/{settlement_id}/customers/{customer_id}` — 结算单客户详情

### 资金端流动性 (1)

- `GET /v1/fund_dashboard` — 资金端流动性看板（资金余额汇总）

### 业务流水表头 (4)

- `GET /v1/biz_transaction_headers/{id}` — 表头详情
- `GET /v1/biz_transaction_headers/{id}/behavior_keyword` — 表头关联行为列表
- `GET /v1/biz_transaction_headers/fund_mark` — 资金标签列表
- `GET /v1/biz_transaction_headers/keyword` — 表头名称列表（ID 查名称）

## 跨域依赖（查询前必读）

- **业务线 `biz_line_id`**：`v_flows*` / `fund_dashboard` / `process_transactions*` / `biz_transactions*` 含 `biz_line_id` 筛选参数时，先到父 skill `references/common-id-mapping.md` 取业务线字典（`GET /v1/biz_lines/keyword`）。字段名陷阱 `biz_line` vs `biz_line_id` vs `biz_line_ids` 详见父 skill。
- **查询链 #2 — 业务流水必经两步**：`biz_transactions*` 的 `transaction_header_id` 必须先从 `biz_transaction_headers/keyword` 取；playbook 见父 skill `references/common-query-chains.md`。
- **对账域 bank / account 翻译**：`r_transactions` / `reconciliation/*` 响应中的 bank / account / platform ID，用父 skill `references/common-id-mapping.md` 的 `accounts/bank/label` / `accounts/platform/label` 映射名称。
- **wrapper 已知问题**：POST 字段静默丢失、PUT/PATCH/DELETE 暂不支持等见父 skill `references/wrapper-caveats.md`。

## 调用模式

**【唯一合法入口】** 所有 armada 调用必须用内置 `bash_exec` 运行父 skill 的 wrapper：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh \
     "$UID" <get|post> <path> [kv 参数...]
```

`"$UID"` 是占位符，agent 在用 `bash_exec` 运行时必须替换为 Step 0（`whoami`）提取的 `sender_id`。Agent **完全不接触** `_meta` 字面值，由 wrapper 内部自动注入（值取自首参传入的 uid）。

**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`（在 blockquote 里作为 ❌ 反例提及允许）。

> NOTE (fleetent): armada 是 fleetent 挂载的 MCP server，原生调用形式为 `armada__armada_get` / `armada__armada_post`；本 skill family 仍统一经 `ns-call.sh` wrapper（`bash_exec` 运行），以注入 `_meta.slackUserId` 做鉴权——直接调用 armada 工具会绕过该注入、生产被拒。reference 文件用内置 `read_file` 读取（或 `bash_exec` 跑 `cat`）。

**示例：**

```bash
# 表头字典（查询链 #2 Step 1）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transaction_headers/keyword"

# 业务流水明细（查询链 #2 Step 2）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/biz_transactions" \
  'query_params={"transaction_header_id": 123, "page": 1, "page_size": 50}'

# 资金端流动性看板
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fund_dashboard" \
  'query_params={"fund_type": 1}'

# FDL 第二步：结算单客户列表
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/fdl-settlements/{settlement_id}/customers" \
  'path_params={"settlement_id": "ST2026031"}'

# 对账：NS 动账流水
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/reconciliation/adjustment/real_transactions/r_flows" \
  'query_params={"start_date": "2026-04-01", "end_date": "2026-04-15", "page": 1, "page_size": 50}'
```

特殊参数格式、wrapper 能力面（仅 get|post，PUT/PATCH/DELETE 暂不支持）详见父 skill。

## 脚本

本 skill 附带两个渲染脚本：

### `scripts/render_biz_transactions.py` — 业务流水明细 TSV 渲染

**为什么需要**：`GET /v1/biz_transactions` 的 `header` 字段动辄数千行（单个枚举字段可含 150+ 候选值），`rows` 字段是 JSON 字符串（非数组）——全量灌入 LLM context 会浪费 token。脚本负责：解析 `rows` JSON 字符串、映射动态字段名 fN → 中文显示名、枚举 id → name、丢弃 `is_used=false` 或本批次全空的列、按 `header.sort` 升序排列。纯标准库，无外部依赖。

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_biz_transactions.py \
  --input /tmp/biz_response.json --output /tmp/biz_render.tsv
```

### `scripts/render_fund_source_stat.py` — 项目资金来源汇总（查本金）TSV 渲染

**为什么需要**：`GET /v1/biz_transactions/stat` 返回三个子表（收入 / 实际资金来源 / 理论资金来源），后两者列数可达 130+，绝大多数列在单项目查询下都为 null；`header` / `rows` 同样是 JSON 字符串。脚本负责：解析 JSON 字符串、对资金来源两表 drop 全 null 列（保留 0 / 空字符串）、收入表原样输出、三表 TSV 用空行分隔。纯标准库，无外部依赖。

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/render_fund_source_stat.py \
  --input /tmp/fund_source.json --output /tmp/fund_source.tsv
```

两个脚本 stdout 都打印单行摘要，TSV 文件直接展示给用户（agent 不加工数值、不重排列顺序）。

### `scripts/query_txid_batch.py` — 批量 TxID 到账反查

**为什么需要**：NS `r_transactions.txid` 是字符串精确匹配字段，**不支持** comma-joined 多 TxID（`{"txid": "h1,h2"}` 会被当成单条字符串做精确匹配，必然零命中）。脚本负责：

- 输入归一化：单参数支持空格 / 逗号 / 换行分隔，长 hex（128/192/256 字符等 64 整数倍且全 hex）自动按 64 切分
- 自动去重保序
- 串行调 `ns-call.sh` 一次一笔，sender_id 透传
- `--also-uncompleted` 标记：先查 `completed`，零命中再查 `uncompleted` 兜底
- 聚合 JSON 输出，含 `to_account_name` / `from_account_name` / `amount` / `currency` / `network` / `transfer_time` / `process_status` / `process_instance_number` 等核心字段

```bash
python3 $SKILLS_DIR/common-ns-flows/scripts/query_txid_batch.py \
  "$UID" "<txid1>" "<txid2>" --also-uncompleted
# 或从文件批量
python3 $SKILLS_DIR/common-ns-flows/scripts/query_txid_batch.py \
  "$UID" --txid-file /tmp/txids.txt
```

Agent 拿到 stdout JSON 后按 §端到端示例：按 TxID 查到账状态 的字段映射表渲染。完整签名、退出码、输入兼容性见脚本头部 docstring。

## references 映射表

| 文件 | 覆盖范围                              |
|------|-----------------------------------|
| `references/transactions-biz-headers.md` | 业务流水列表 / 汇总 / 表头字典 / 行为关键词 / 资金标签 |
| `references/biz-transactions-fund-source-stat.md` | 项目资金来源汇总（查本金）/ 实际+理论资金来源 stat 接口  |
| `references/transactions-logical.md` | 逻辑交易流水 / 逻辑账户流水                   |
| `references/transactions-v-flows-dashboard.md` | 资产端概览 / 资金端概览 / 资金端本金 / 资产分布快照    |
| `references/transactions-real-reconciliation.md` | 实际交易流水 / NS 动账 / 中台侧动账 / 账户余额核对   |
| `references/transactions-fdl.md` | FDL 三步结算                          |
| `references/fund-dashboard.md` | 资金端流动性看板 + 流程流水（看板场景）             |

读取方式：

```bash
cat $SKILLS_DIR/common-ns-flows/references/{文件名}
```

父 skill 公共 references（`common-conventions.md` / `common-id-mapping.md` / `common-query-chains.md` / `wrapper-caveats.md`）仍在父目录，按需读取：

```bash
cat $SKILLS_DIR/common-ns-system-query/references/{公共文件名}
```

## 端到端示例：查 BP-Pay 业务线业务流水

**用户**：查一下 BP-Pay 的业务流水。

**执行步骤**：

1. Step 0 鉴权预检（略）

2. 业务线根依赖：拉业务线字典（若本轮未缓存）

   ```bash
   bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
     get "/v1/biz_lines/keyword"
   ```

   → 取到 `BP-Pay` 对应的 `biz_line_id`。

3. 查询链 #2 Step 1：取业务流水表头字典，找到 BP-Pay 对应的 `transaction_header_id`

   ```bash
   bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
     get "/v1/biz_transaction_headers/keyword"
   ```

4. 查询链 #2 Step 2：用拿到的 `transaction_header_id` 调业务流水明细，响应落盘

   ```bash
   bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
     get "/v1/biz_transactions" \
     'query_params={"transaction_header_id": 123, "page": 1, "page_size": 50}' \
     > /tmp/biz_response.json
   ```

5. 用渲染脚本生成 TSV

   ```bash
   python3 $SKILLS_DIR/common-ns-flows/scripts/render_biz_transactions.py \
     --input /tmp/biz_response.json --output /tmp/biz_render.tsv
   ```

6. 展示 TSV 内容给用户（按父 skill §输出规范：中文字段名、无中文注释字段跳过、字段值原样输出、不得拆分/解析/二次加工）。

## 端到端示例：按 TxID 查到账状态（**最高频场景之一**）

**用户**：查一下 TxID `40b236966a87a819aaa5d6b5ab0896ea75ac7d30c2ae2101d0367ea46841d2d4` 的资金到账情况。

**为什么必须用本 skill 而不是中台 `bs-transaction-history`**：

- 中台 `transaction_list_account_transactions.tx_id` 必须配合 `account_id` 或 `account_code`（后端防全表扫描），用户没提供账户上下文就用不了
- NS `r_transactions.txid` **不强制账户/业务线上下文**，是全局反查的唯一入口

> 🔴 **致命反例**：`r_transactions.txid` 是**字符串精确匹配**字段，**严禁** comma-joined 多 TxID：
>
> ```bash
> # ❌ 这样会被当成单条精确匹配，必然零命中
> get "/v1/r_transactions" \
>   'query_params={"txid": "hash1,hash2", "page": 1, "page_size": 50}'
> ```
>
> 必须逐笔单独查。本 skill 提供了 `scripts/query_txid_batch.py` 把"逐笔串行 + 聚合"封装好，**不要手写 loop**。

**推荐路径：用 batch 脚本（一次调用搞定多笔）**

```bash
# Step 0 — sender_id 已用 whoami 取到 $UID（详见父 skill Step 0）

# Step 1 — 直接调 batch 脚本
python3 $SKILLS_DIR/common-ns-flows/scripts/query_txid_batch.py \
  "$UID" \
  "40b236966a87a819aaa5d6b5ab0896ea75ac7d30c2ae2101d0367ea46841d2d4" \
  "caa440f58cf81a06d85120a800317d7627c7689a493430e5f2b468f8c60bb9e9" \
  --also-uncompleted
```

输入兼容性（脚本自动处理，agent 无需预处理）：

| 用户原始输入 | 脚本行为 |
|---|---|
| `"hash1 hash2"` 空格分隔 | 拆 2 笔 |
| `"hash1,hash2"` 逗号分隔 | 拆 2 笔 |
| `"hash1\nhash2"` 换行分隔 | 拆 2 笔 |
| `"hash1hash2"` 128 字符黏在一起且都是 hex（典型 Slack 复制场景）| 按 64 切分为 2 笔 |
| 重复 TxID | 自动去重保序 |

`--also-uncompleted` 标记：先查 `completed`（已完成表），对零命中的 TxID 再查 `uncompleted`（实时表）确认在途。

脚本输出（stdout）：

```json
{
  "status": "ok",
  "total_txids": 2,
  "results": [
    {
      "txid": "40b2369...d2d4",
      "process_status": "completed",
      "hit_count": 1,
      "summary": [
        {
          "txid": "40b2369...d2d4",
          "to_account_name": "alpha-bn-spot",
          "from_account_name": "external",
          "amount": "1000.50",
          "currency": "USDT",
          "network": "ERC20",
          "transfer_time": "2026-05-15T10:23:11Z",
          "process_status": "completed",
          "process_instance_number": "20260515003"
        }
      ]
    },
    {
      "txid": "caa440f...b9e9",
      "process_status": "completed",
      "hit_count": 0,
      "summary": []
    }
  ]
}
```

**Step 2 — agent 渲染**：从脚本输出按下表中文化展示：

```
| TxID | 收款方 | 付款方 | 金额 | 币种 | 网络 | 链上时间 | 状态 | 关联流程号 |
|------|--------|--------|------|------|------|---------|------|-----------|
```

字段映射：`to_account_name`→收款方 / `from_account_name`→付款方 / `amount`→金额 / `currency`→币种 / `network`→网络 / `transfer_time`→链上时间（UTC→UTC+8 展示）/ `process_status`→状态（`completed`=已确认到账 / `uncompleted`=在途）/ `process_instance_number`→关联流程号。

零命中的 TxID 单独一行说明：

```
未在 NS r_transactions 找到 TxID `<X>` 的记录。可能原因：
- 该 TxID 不属于公司任何账户的链上交易（外部转账，NS 未记账）
- TxID 输入错误（请用户复核 hash）
- 极罕见：NS 还未同步链上事件

如需进一步追踪，请提供：收款方账户名 / 业务线 / 大致时间窗口，
我会 fallback 到中台 bs-transaction-history 用 account_id + tx_id 精查。
```

---

**Fallback 路径（仅当 batch 脚本不可用时）：手写逐笔调 wrapper**

```bash
# 逐笔，每个 TxID 独立一次调用
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/r_transactions" \
  'query_params={"txid": "40b2369...d2d4", "process_status": "completed",
                 "page": 1, "page_size": 50}'

bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/r_transactions" \
  'query_params={"txid": "caa440f...b9e9", "process_status": "completed",
                 "page": 1, "page_size": 50}'
```

**关键提醒**：

- **严禁** 把多个 TxID 用逗号拼成一个字符串塞给 `txid` 字段（NS 后端不会拆分匹配，只会做整字符串精确匹配，必然零命中）
- **严禁** 调中台 `transaction_list_account_transactions` 做纯 TxID 查询——它强制要求 `account_id`/`account_code`，且只看公司账户入账，看不到链路全貌
