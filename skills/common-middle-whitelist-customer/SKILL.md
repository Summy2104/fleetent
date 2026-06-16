---
name: common-middle-whitelist-customer
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台**客户白名单**（外部对手方地址）查询（middle-mcp
  `customer_white_list_customer_whitelist` +
  `customer_white_get_customer_whitelist`）。对应中台实体
  `CustomerWhiteList`，承载外部客户提交的收款地址、风险评级、
  合规建议等。后端隐式过滤：仅返回终审通过 + 状态正常 + 未删除的有效记录。
  仅查询，不协同——外部白名单流程对接请走 NS 侧
  `bs-external-whitelist-coordinating`。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: BS Team
  version: 1.0.0
complexity: L1
---

# 中台客户白名单查询（Customer Whitelist Query）

> ⛔ **执行前强制约束**（hub `common-middle-system-query` §共通强制约束的子集）
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 hub wrapper 自动注入。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **严禁绕过 wrapper**：所有中台 MCP 调用必须通过 `$SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh`，**使用 `--args` JSON 模式**（见 hub `wrapper-caveats.md` §1）。
> 5. **地址原字面**：钱包地址 / TxnID 等加密哈希原样输出，禁止截断 / 缩写 / 大小写转换。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "查客户 ABC Trading 的白名单地址"
  - "客户 ID 42 的所有收款地址" / "查外部对手方白名单"
  - "查高风险客户白名单" / "OTC 业务线下的客户白名单"
  - "查客户白名单 1234 详情" / 「合规建议是什么」
- **被其它 skill 调用**：风控 / 出款审核类 skill 在做"外部地址合规校验"时查客户白名单库。

## 后端隐式过滤（必读）

中台后端**始终**在查询前隐式追加以下过滤条件，agent 看到的永远是有效记录子集：

| 隐式过滤 | 含义 |
|---------|------|
| `is_delete=0` | 未删除 |
| `audit_status=60`（终审通过）| 已完成终审 |
| `state="1"`（正常）| 启用状态 |
| `dept_belong_id ∈ ("22","999")` | 部门归属 |

**含义**：本 skill 查不到「待审核 / 已删除 / 归档 / 黑名单」的客户白名单——它们对 agent 不可见。如果用户问"我刚提交的客户白名单去哪了"，可能是隐式过滤把它过滤掉了，应引导用户去 NS 侧 `bs-external-whitelist-coordinating` 查协同状态。

## 能力边界

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 查询**客户**白名单（CustomerWhiteList，外部对手方）| ✅ | — |
| 客户白名单详情（含 `risk_reason` / `compliance_recommendations` 等合规字段）| ✅ | — |
| **内**白名单（WhiteListV2，公司自有地址）| ❌ | `common-middle-whitelist-internal` |
| 协同**外部**白名单流程（客户提交、审核回执）| ❌ | `bs-external-whitelist-coordinating`（NS 侧） |
| **起草**内白名单邮件 | ❌ | `bs-internal-whitelist-drafting`（NS 侧） |
| 转账地址合规校验（出款前是否允许）| ⚠️ 本 skill 只返回白名单条目 + 风险评级，最终合规判定由风控综合决定 | `safe-tx-hash` + 风控规则 |
| 客户主数据（公司信息 / 联系方式）| ❌ | `common-ns-masterdata`（NS 侧客户档案）|

## 调用模式

所有中台 MCP 调用必须通过 hub wrapper（用内置 `bash_exec` 工具运行下列命令）：

```bash
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
     <tool_name> '<args_json>'
```

**示例**（经 `bash_exec`）：

```bash
# 1) 按客户名模糊 + 币种过滤
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  customer_white_list_customer_whitelist \
  '{"customer_name": "ABC", "coin": "USDT", "page": 1, "page_size": 50}'

# 2) 按客户 ID + 业务线过滤
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  customer_white_list_customer_whitelist \
  '{"customer_id": 42, "business_id": 5, "page": 1, "page_size": 20}'

# 3) 按风险等级过滤（3 = 高风险）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  customer_white_list_customer_whitelist '{"risk": 3, "page_size": 50}'

# 4) 详情（按 ID）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  customer_white_get_customer_whitelist '{"whitelist_id": 1234}'
```

> NOTE (fleetent): 中台 middle-mcp 在 my-bot 上无对应的原生 MCP server；中台访问统一经 hub `common-middle-system-query` 的 `middle-call.sh` wrapper（由内置 `bash_exec` 在沙箱内运行）。

## 输入参数

### `customer_white_list_customer_whitelist`（列表）

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `address` | string | — | 地址模糊匹配（icontains） |
| `customer_id` | int | — | 客户主体 ID 精确匹配（来自 `common-ns-masterdata` 客户档案） |
| `customer_name` | string | — | 客户全名模糊匹配 |
| `coin` | string | — | 币种 code 精确匹配（如 `USDT` / `BTC`） |
| `chain_id` | int | — | 网络 ID 精确匹配（可走 `common-middle-dict` 解析） |
| `business_id` | int | — | 业务线 ID 精确匹配（来自 `common-ns-masterdata` 业务线） |
| `risk` | int | — | 风险等级：0 无风险 / 1 低 / 2 中 / 3 高 / 4 严重 |
| `page` | int | `1` | 页码 |
| `page_size` | int | `20` | 每页条数，上限 100 |

### `customer_white_get_customer_whitelist`（详情）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `whitelist_id` | int | **是** | `CustomerWhiteList` 主键 |

**详情比列表多 7 字段**：`description` / `remark` / `fingerprint` / `email_title` / `risk_reason` / `risk_updatetime` / `compliance_recommendations`

## 用户输入解析

- 用户给"客户 X" / "对手方 X" / "外部 X" → `customer_name=<X>` 模糊匹配
- 用户给"客户 ID X" / "customer_id X"（纯数字 + 客户上下文）→ `customer_id=<X>` 精确匹配
- 用户给地址 → `address=<原文>` 模糊匹配
- 用户给币种符号（`USDT` / `BTC` / `ETH`）→ `coin=<原文>` 精确匹配
- 用户给链名 → 先调 `common-middle-dict` 取 `chain_id`；命中失败 `ℹ️` 标注未识别
- 用户给业务线名 → 需先调 `common-ns-masterdata` 解析 `business_id`；NL 直接给数字业务线 ID → `business_id=<原文>`
- 用户给"高风险" / "严重风险" / "无风险" → `risk=3` / `risk=4` / `risk=0`
- 用户给纯数字 + "白名单 ID" 上下文 → 走 `customer_white_get_customer_whitelist` `whitelist_id=<原文>`
- 用户给 `top N` / `前 N` → `page_size=min(N, 100)`
- 用户未指定任何过滤 → 直接默认 `page=1 page_size=20`

## 工作流程

### Step 0 — 路由判断（list vs get）

- 用户给"白名单 ID `<数字>`" 或 "查 ID 1234 详情" → `customer_white_get_customer_whitelist`
- 用户给过滤条件（客户 / 地址 / 币种 / 风险 / 业务线 / 链）→ `customer_white_list_customer_whitelist`
- 两者皆有 → 优先 detail，并在尾部 `ℹ️` 标注「忽略过滤条件，按 whitelist_id 查单条」

### Step 1 — 调用主接口

按 §输入参数 解析过滤字段。**字段无法识别 → 不传，不追问**。`chain_id` / `business_id` 若需名→ID 转换，先调对应辅助 spoke。

### Step 2 — 字段映射

中台返回字段以 OpenAPI 为准。FK 字段（`customer_id` / `chain_id` / `business_id`）通常返回 `{id, code, name}` 或客户/业务的扩展 brief；枚举字段（`risk`）已附 `*_display` 中文文案，**直接展示 `*_display`，不要二次解析数字码**。

### Step 3 — 渲染输出

**列表模式**：Markdown 表格 + 末尾分页总览 `共 N 条，第 X 页 / 共 Y 页（page_size=Z）`。

列固定建议：

```
| ID | 地址 | 客户 | 币种 | 链 | 业务线 | 风险等级 |
```

**详情模式**：键值表逐字段展开。列表外的 7 个扩展字段（含 `risk_reason` / `compliance_recommendations` 等合规字段）作为独立"合规信息"段落呈现。

### Step 4 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `customer_white_get_customer_whitelist` 缺 `whitelist_id` | 追问：「请提供客户白名单 ID（纯数字主键）」|
| `whitelist_id` 不存在 | 「客户白名单 `<id>` 不存在或被隐式过滤（未终审通过 / 已归档 / 已删除）」|
| stderr 含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| stderr 含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| stderr 含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| stderr 含 `timeout` / `connection refused` | 重试 1 次 |
| 列表为空 | 「未查到符合条件的客户白名单（过滤条件：...）。注意后端只返回终审通过的有效记录；如查不到，可能是审核未完成，请走 NS 侧 `bs-external-whitelist-coordinating` 查协同状态。」 |
| 其它非 0 退出 | 透传 stderr |

## 输出示例

**列表**：

```
| ID   | 地址                                       | 客户         | 币种 | 链  | 业务线 | 风险等级 |
|------|-------------------------------------------|--------------|------|-----|-------|---------|
| 1234 | 0xabc1234567890abcdef1234567890abcdef1234 | ABC Trading  | USDT | ETH | OTC   | 低风险  |
| 1235 | 0xdef9876543210fedcba9876543210fedcba9876 | ABC Trading  | USDT | TRX | OTC   | 无风险  |

共 5 条，第 1 页 / 共 1 页（page_size=20）
```

**详情**：

```
| 字段 | 值 |
|------|----|
| ID | 1234 |
| 地址 | 0xabc1234567890abcdef1234567890abcdef1234 |
| 客户 | ABC Trading (id=42) |
| 币种 | USDT |
| 链 | ETH (id=1) |
| 业务线 | OTC (id=5) |
| 风险等级 | 低风险 |

### 合规信息
| 字段 | 值 |
|------|----|
| 描述 (description) | 客户提交的接收地址 |
| 备注 (remark) | 业务方已确认 |
| 指纹 (fingerprint) | ... |
| 邮件标题 (email_title) | [Whitelist Submission] ABC Trading - USDT-ETH |
| 风险说明 (risk_reason) | TRM 扫描无命中 |
| 风险更新时间 (risk_updatetime) | 2026-04-15 10:23:11 UTC+8 |
| 合规建议 (compliance_recommendations) | 可放行 |
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `customer_white_list_customer_whitelist` | 客户白名单列表 |
| `customer_white_get_customer_whitelist` | 客户白名单详情（+7 字段）|

> 工具命名详情、参数清单见 `common-middle-system-query/references/common-tool-naming.md` §2.8。

## 不做（边界）

- 不查内白名单（→ `common-middle-whitelist-internal`）
- 不**协同**外部白名单流程（→ `bs-external-whitelist-coordinating` NS 侧）
- 不**起草**内白名单邮件（→ `bs-internal-whitelist-drafting` NS 侧）
- 不查客户主数据 / 联系方式（→ `common-ns-masterdata`）
- 不做转账合规判定（→ `safe-tx-hash` + 风控）
- 不创建 / 修改 / 删除任何白名单条目（只读 GET）
- 不展示未终审通过的客户白名单（后端隐式过滤）

## 本 skill 文件结构

```
skills/common-middle-whitelist-customer/
├── SKILL.md
└── SKILL.tests.yaml
```

> wrapper 收敛在 `common-middle-system-query/scripts/middle-call.sh`，工具清单见 `common-middle-system-query/references/common-tool-naming.md` §2.8。
