---
name: common-middle-whitelist-internal
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台**内白名单**（公司内部地址）查询（middle-mcp `white_list_whitelist` +
  `white_get_whitelist`）。对应中台实体 `WhiteListV2`，承载公司自有钱包地址、
  审核状态、启用状态等。仅查询，不起草——起草内白名单邮件请走 NS 侧
  `bs-internal-whitelist-drafting`。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: BS Team
  version: 1.0.0
complexity: L1
---

# 中台内白名单查询（Internal Whitelist Query）

> ⛔ **执行前强制约束**（hub `common-middle-system-query` §共通强制约束的子集）
> 1. 必须读完本文档再调用 MCP；不得凭记忆猜测参数。
> 2. **严禁** 直接 `curl` 中台 HTTP 端点；鉴权由 hub wrapper 自动注入。
> 3. **严禁** 在回复或日志里输出 `Authorization` / `Bearer` / `X-API-Key` 任何片段。
> 4. **严禁绕过 wrapper**：所有中台 MCP 调用必须通过 `$SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh`，**使用 `--args` JSON 模式**（见 hub `wrapper-caveats.md` §1）。
> 5. **地址原字面**：钱包地址 / TxnID 等加密哈希原样输出，禁止截断 / 缩写 / 大小写转换。

## 使用场景

- **NL 触发**（hub 路由后进入）：
  - "查一下内白名单里有没有 `0x...`" / "USDT 内白名单列表"
  - "查公司主体 NS Trading 的内白名单"
  - "已归档的内部白名单" / "Binance 平台上待审核的内白名单"
- **被其它 skill 调用**：风控 / 出款审核类 skill 在做"自有地址合规校验"时查内白名单库。

## 能力边界

| 用户意图 | 用本 skill | 改用 |
|---------|----------|------|
| 查询**内**白名单（WhiteListV2，公司自有地址）| ✅ | — |
| 内白名单详情（含 remark / address_tag / deposit_address / uid 等 8 个扩展字段）| ✅ | — |
| **客户**白名单（外部对手方地址，含风险评级 / 合规建议）| ❌ | `common-middle-whitelist-customer` |
| **起草**内白名单邮件（NL → 模板填充 → 发邮件） | ❌ | `bs-internal-whitelist-drafting`（NS 侧） |
| 协同**外部**白名单流程（客户提交、审核回执）| ❌ | `bs-external-whitelist-coordinating`（NS 侧）|
| 转账地址合规校验（出款前是否允许）| ⚠️ 本 skill 只返回白名单条目，合规判定由风控综合决定 | `safe-tx-hash` + 风控规则 |
| 地址标签 / 地址簿（地址 → 含义解析） | ❌ | `common-ns-masterdata`（NS 侧地址标签） |

## 调用模式

所有中台 MCP 调用必须通过 hub wrapper（用内置 `bash_exec` 工具运行下列命令）：

```bash
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
     <tool_name> '<args_json>'
```

**示例**（经 `bash_exec`）：

```bash
# 1) 按地址 + 币种过滤
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  white_list_whitelist '{"address": "0x1234", "coin": "USDT", "page": 1, "page_size": 50}'

# 2) 按主体名过滤（公司主体 subject）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  white_list_whitelist '{"subject": "NS Trading", "page": 1, "page_size": 20}'

# 3) 按审核状态过滤（3 = 待审核）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  white_list_whitelist '{"audit_status": 3, "page": 1, "page_size": 50}'

# 4) 详情（按 ID）
bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
  white_get_whitelist '{"whitelist_id": 789}'
```

> NOTE (fleetent): 中台 middle-mcp 在 my-bot 上无对应的原生 MCP server；中台访问统一经 hub `common-middle-system-query` 的 `middle-call.sh` wrapper（由内置 `bash_exec` 在沙箱内运行）。

## 输入参数

### `white_list_whitelist`（列表）

| 参数 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `address` | string | — | 地址模糊匹配（icontains） |
| `subject` | string | — | 主体名称模糊匹配（公司主体，如 `NS Trading` / `Alpha Holdings`） |
| `coin` | string | — | 币种 code 精确匹配（如 `USDT` / `BTC`） |
| `chain_id` | int | — | 网络 ID 精确匹配（来自 `common_list_chains`，可走 `common-middle-dict` 解析） |
| `market_id` | int | — | 平台 ID 精确匹配（CEX 平台见 hub §Market ID 映射）|
| `audit_status` | int | — | 1 待认证 / 2 认证不通过 / 3 待审核 / 4 审核不通过 / 5 审核不通过(认证) / 6 审核通过 |
| `state` | int | — | 1 正常 / 2 归档 / 3 废弃 / 4 黑名单 |
| `page` | int | `1` | 页码 |
| `page_size` | int | `20` | 每页条数，上限 100 |

### `white_get_whitelist`（详情）

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `whitelist_id` | int | **是** | `WhiteListV2` 主键 |

**详情比列表多 8 字段**：`remark` / `msg` / `fingerprint` / `address_tag` / `uid` / `deposit_address` / `tag_info` / `account_owner`

## 用户输入解析

- 用户给地址（`0x` 前缀 EVM / `T` 前缀 TRON / 等长哈希）→ `address=<原文>` 模糊匹配
- 用户给币种符号（`USDT` / `BTC` / `ETH`）→ `coin=<原文>` 精确匹配
- 用户给"主体 X" / "公司主体 X" / "Subject X" → `subject=<X>` 模糊匹配
- 用户给链名 / 平台名 → 先调 `common-middle-dict` 取 `chain_id` / 平台用 hub 硬编码 market_id；命中失败 `ℹ️` 标注未识别
- 用户给纯数字 + "白名单 ID" 上下文 → 走 `white_get_whitelist` `whitelist_id=<原文>`
- 用户给"待审核" / "审核未通过" / "审核通过" → `audit_status=3` / `4` / `6`
- 用户给"已归档" / "黑名单" / "废弃" → `state=2` / `4` / `3`
- 用户给 `top N` / `前 N` → `page_size=min(N, 100)`
- 用户未指定任何过滤 → 直接默认 `page=1 page_size=20`

## 工作流程

### Step 0 — 路由判断（list vs get）

- 用户给"白名单 ID `<数字>`" 或 "查 ID 789 详情" → `white_get_whitelist`
- 用户给过滤条件（地址 / 主体 / 币种 / 状态 / 链 / 平台）→ `white_list_whitelist`
- 两者皆有 → 优先 detail，并在尾部 `ℹ️` 标注「忽略过滤条件，按 whitelist_id 查单条」

### Step 1 — 调用主接口

按 §输入参数 解析过滤字段。**字段无法识别 → 不传，不追问**。`chain_id` / `market_id` 若需名→ID 转换，先调辅助 spoke。

### Step 2 — 字段映射

中台返回字段以 OpenAPI 为准。FK 字段（`chain_id` / `market_id`）通常返回 `{id, code, name}` 三元组；枚举字段（`audit_status` / `state`）已附 `*_display` 中文文案，**直接展示 `*_display`，不要二次解析数字码**。

### Step 3 — 渲染输出

**列表模式**：Markdown 表格 + 末尾分页总览 `共 N 条，第 X 页 / 共 Y 页（page_size=Z）`。

列固定建议：

```
| ID | 地址 | 币种 | 链 | 平台 | 主体 | 审核状态 | 启用状态 |
```

**详情模式**：键值表逐字段展开。列表外的 8 个扩展字段作为独立"扩展信息"段落呈现。

### Step 4 — 错误处理

| 错误场景 | 反馈 |
|---------|------|
| `white_get_whitelist` 缺 `whitelist_id` | 追问：「请提供内白名单 ID（纯数字主键）」|
| `whitelist_id` 不存在 | 「内白名单 `<id>` 不存在或无权限访问」 |
| stderr 含 `401` / `403` | `{status:"error", reason:"missing_or_invalid_api_key"}` |
| stderr 含 `unknown server` / `server not found` | `{status:"error", reason:"middle_mcp_not_registered"}` |
| stderr 含 `unknown tool` / `tool not found` | `{status:"error", reason:"middle_mcp_tool_missing"}` |
| stderr 含 `timeout` / `connection refused` | 重试 1 次 |
| 列表为空 | 「未查到符合条件的内白名单（过滤条件：...）」 |
| 其它非 0 退出 | 透传 stderr |

## 输出示例

**列表**：

```
| ID  | 地址                                       | 币种 | 链  | 平台    | 主体        | 审核状态 | 启用状态 |
|-----|-------------------------------------------|------|-----|---------|------------|---------|---------|
| 789 | 0x742d35Cc6634C0532925a3b844Bc454e4438f44e | USDT | ETH | Binance | NS Trading | 审核通过 | 正常    |

共 3 条，第 1 页 / 共 1 页（page_size=20）
```

**详情**：

```
| 字段 | 值 |
|------|----|
| ID | 789 |
| 地址 | 0x742d35Cc6634C0532925a3b844Bc454e4438f44e |
| 币种 | USDT |
| 链 | ETH (id=1) |
| 平台 | Binance (id=4) |
| 主体 | NS Trading |
| 审核状态 | 审核通过 |
| 启用状态 | 正常 |

### 扩展信息
| 字段 | 值 |
|------|----|
| 备注 (remark) | ... |
| 备忘 (msg) | ... |
| 指纹 (fingerprint) | ... |
| 地址标签 (address_tag) | ... |
| UID | ... |
| 充值地址 (deposit_address) | ... |
| 标签信息 (tag_info) | ... |
| 开户主体 (account_owner) | ... |
```

## 依赖 MCP 工具

| 工具 | 用途 |
|------|------|
| `white_list_whitelist` | 内白名单列表 |
| `white_get_whitelist` | 内白名单详情（+8 字段） |

> 工具命名详情、参数清单见 `common-middle-system-query/references/common-tool-naming.md` §2.7。

## 不做（边界）

- 不查客户白名单（→ `common-middle-whitelist-customer`）
- 不**起草**内白名单邮件（→ `bs-internal-whitelist-drafting` NS 侧）
- 不做地址标签 / 地址簿（→ `common-ns-masterdata`）
- 不做转账合规判定（→ `safe-tx-hash` + 风控）
- 不创建 / 修改 / 删除任何白名单条目（只读 GET）
- 不做跨链地址自动识别（地址解析由用户提供）

## 本 skill 文件结构

```
skills/common-middle-whitelist-internal/
├── SKILL.md
└── SKILL.tests.yaml
```

> wrapper 收敛在 `common-middle-system-query/scripts/middle-call.sh`，工具清单见 `common-middle-system-query/references/common-tool-naming.md` §2.7。
