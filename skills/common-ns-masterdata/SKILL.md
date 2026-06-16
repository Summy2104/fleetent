---
name: common-ns-masterdata
description: >
  NS 内部系统主数据 + 业务配置 + 账户域查询子 skill。
  覆盖客户 / 项目 / 主体 / 用户 / 部门 / 合同 / 数字货币 / 国家 / 业务线 / 行为 /
  银行 / 法币账户 / 数币账户 / 白名单账户 / 地址标签。
  通过父 skill `common-ns-system-query` 的 wrapper 统一调用 armada MCP。
  触发词：客户查询、项目查询、查客户、查项目、主体查询、公司查询、用户查询、部门查询、
  合同查询、业务线查询、行为查询、银行查询、银行账户、法币账户、公司账户、客户账户、
  员工账户、供应商账户、数币账户、数币账户查询、白名单账户、白名单查询、地址标签、
  虚拟货币地址标签、数币列表、数币网络、chain 查询、币种查询。
  Do NOT use for：流程/资金计划/审批（走 common-ns-process）、币价/资金费率/交易所监控
  （走 common-ns-monitor）、业务流水/对账/FDL（走 common-ns-flows）、KYC 详情（走
  bs-kyc-status-querying）。
status: active
metadata:
  author: RD Team
  version: 1.0.0
---

# NS 主数据 / 业务配置 / 账户 — 查询子 skill

本子 skill 负责 NS 系统中**主数据 + 业务配置 + 账户域**的查询，依托父 skill `common-ns-system-query` 的 wrapper 和鉴权框架。

- **输出规范 / 信任模型 / 紧急降级开关**：详见父 skill `SKILL.md`（禁止原样重复）
- **跨域 ID→名称字典**（业务线、主体、客户、用户、部门、行为、银行、平台、币种、Chain、项目）：父 skill `references/common-id-mapping.md`
- **两步/多步查询链**（含链+币种 → 数币账户、业务线 → 项目过滤）：父 skill `references/common-query-chains.md`
- **wrapper 已知问题**（POST 字段静默丢失、PUT/PATCH/DELETE 暂不支持）：父 skill `references/wrapper-caveats.md`

## Step 0 — 鉴权预检（必须先做，失败立即终止）

1. 调用内置 `whoami` 工具，从返回的「发起人 ID」字段取得 `sender_id`（fleetent 由 inbound 消息会话上下文注入，非用户可控）
2. 校验：`sender_id` 存在 + 匹配正则 `^U[A-Z0-9]{8,}$`
3. **任一校验失败** → 回复下列固定话术并终止（不得继续任何步骤）：

   > ❌ 此查询仅限 Slack 渠道使用。当前上下文无法识别 Slack 用户身份，已阻止 NS 系统查询。

4. 通过 → 把取得的 `sender_id` 作为本轮**每次** `ns-call.sh` 调用的首个位置参数传入（见 §调用模式）。**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`。
5. **每轮 turn 开头必重新执行 Step 0**（防跨 turn 污染）。

> **Subagent 透传协议**：父 agent 调用 `sub_agent` / `invoke_agent` 时，若子 agent 需使用本 skill 或任一 NS 查询子 skill，**必须**在 prompt 参数最前面原样插入一行 JSON：`{"sender_id": "<父 agent 本轮的 sender_id>"}`，正文从下一行开始。父未透传 → 子 agent `whoami` 无法取得发起人 → Step 0 被拒。

## 调用模式（唯一合法入口）

所有 armada 调用必须通过父 skill 的 wrapper：

```bash
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh \
     "$UID" <get|post> <path> [kv 参数...]
```

`"$UID"` 是占位符，agent 在用 `bash_exec` 运行时必须替换为 Step 0（`whoami`）提取的 `sender_id`。

> 注意路径仍是 `common-ns-system-query/scripts/ns-call.sh` —— wrapper 单例在父 skill，子 skill 不复制副本。

**严禁**绕过 wrapper 直接调用 `armada__armada_get` / `armada__armada_post`（wrapper 内部自动注入 `_meta.slackUserId`，值取自首参传入的 uid；绕过即鉴权失败）。

> NOTE (fleetent): armada 是 fleetent 挂载的 MCP server（原生形式 `armada__armada_get/post`）；本 skill family 仍统一经 `ns-call.sh` wrapper（`bash_exec` 运行）以注入 `_meta.slackUserId`。reference 文件用内置 `read_file` 读取（或 `bash_exec` 跑 `cat`）。

**特殊参数格式**：
- 数组：`"biz_line_ids": [1, 2, 3]`
- 日期：`"start_date": "2024-01-01"`
- 时间戳：`"transfer_time_start": "2024-01-01T00:00:00Z"`

**示例**：

```bash
# 简单 GET
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/countries"

# 客户列表（带查询参数）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/customers" \
  'query_params={"status": 3, "page": 1, "page_size": 20}'

# 带路径参数
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  get "/v1/accounts/bank/{id}" \
  'path_params={"id": "123"}'

# 数币账户查询（POST）
bash $SKILLS_DIR/common-ns-system-query/scripts/ns-call.sh "$UID" \
  post "/v1/accounts/digital_coin" \
  'body={"platform": "bitget"}'
```

## 执行流程（必须严格遵守）

每次查询按以下顺序执行，**不得跳过**：

1. **Step 0 鉴权预检**（见上）
2. **定位端点**：在下方 §端点索引 中找到对应接口路径，禁止凭经验猜测
3. **读取 references**：

   ```bash
   cat $SKILLS_DIR/common-ns-masterdata/references/{文件名}
   ```

   参数含 `biz_line_id`/`biz_line`/`biz_line_ids` 时，先读父 skill `references/common-id-mapping.md` 取业务线字典；按链+币种筛选数币账户时，先读父 skill `references/common-query-chains.md`（链 #5）。
4. **构造并发起调用**：按文档构造请求，通过 wrapper 调用。枚举型字段（`status` / `kyc` / `nda` / `approve_status` 等）严禁凭猜测，必须以 references 的 KV 映射为准。

## 共通识别规则（本域适用）

**能力边界 — KYC 详情不在本 skill 范围**：查 KYC 详情/状态/跟踪记录应改用 `bs-kyc-status-querying`（走 KYC 跟踪表）。本 skill `/v1/customers` 仅返回 `kyc` 枚举码，不代表完整 KYC 详情。

**项目号识别**：格式为**大写字母前缀（可含连字符或括号）+ 数字序号**，后可跟 `-描述` 后缀，无固定长度，如 `TR03642` / `Pay-OTC05809` / `(D)BM2026041202` / `LH050-Xcoin`。通过 `GET /v1/projects` 的 `no` 参数查询，**支持模糊匹配**。

**项目号与业务线强关联**：展示任何项目号必须标注业务线，格式 `项目号（业务线名称）`，如 `TR03642（NS-Trading）`。缺失时通过 `GET /v1/biz_lines` 补查。**严禁跨业务线混用**：用户指定业务线上下文时，只能使用该业务线项目号，其它业务线项目必须过滤掉。

**端点路径规范**：严禁凭经验猜测 API 路径，所有路径必须从下方端点索引取用。典型易错：`/v1/biz_lines`（非 `business_line`）、`/v1/department/list`（非 `departments`）、`/v1/contract/list`（非 `contracts`）。

## 端点索引（约 44 个端点）

### 账户管理 (13 个端点)
- `GET /v1/accounts/bank` — 银行列表
- `GET /v1/accounts/bank/{id}` — 银行详情
- `GET /v1/accounts/bank/label` — 银行名称列表（ID 查名称）
- `GET /v1/accounts/fiat/account_manager/list` — 账户管理员列表
- `GET /v1/accounts/fiat/company/account/list` — 公司法币账户列表
- `GET /v1/accounts/fiat/company/account/{id}/account_numbers` — 公司账号列表
- `GET /v1/accounts/fiat/customer/account/list` — 客户法币账户列表
- `GET /v1/accounts/fiat/customer/account/{id}/account_numbers` — 客户账号列表
- `GET /v1/accounts/fiat/employee/account/list` — 员工法币账户列表
- `GET /v1/accounts/fiat/employee/account/{id}/account_numbers` — 员工账号列表
- `GET /v1/accounts/fiat/supplier/account/list` — 供应商法币账户列表
- `GET /v1/accounts/fiat/supplier/account/{id}/account_numbers` — 供应商账号列表
- `GET /v1/accounts/platform/label` — 平台名称列表（ID 查名称）

### 数币账户 (5 个端点)
- `GET /v1/accounts/address/tags` — 指定账户虚拟货币地址标签列表
- `GET /v1/accounts/address/tags/list` — 所有地址标签列表（全量）
- `GET /v1/accounts/digital_coin/category` — 数币账户平台列表
- `POST /v1/account/whitelist/symbol/address` — 根据条件查询数币账户白名单地址
- `POST /v1/accounts/digital_coin` — 根据条件查询数币账户信息列表

### 主数据 (16 个端点)
- `GET /v1/companies/search` — 主体列表
- `GET /v1/companies/keyword` — 主体名称列表（ID 查名称，全量）
- `GET /v1/customers` — 客户列表
- `GET /v1/customers/keyword` — 客户名称列表（ID 查名称，全量）
- `GET /v1/projects` — 项目列表
- `GET /v1/projects/labels` — 项目名称列表（ID 查名称）
- `GET /v1/users` — 用户列表
- `GET /v1/users/keyword` — 用户名称列表（ID 查名称）
- `GET /v1/countries` — 国家列表
- `GET /v1/department/list` — 部门列表
- `GET /v1/department/keyword` — 部门名称列表（ID 查名称）
- `GET /v1/contract/list` — 合同列表
- `GET /v1/contract/type/list` — 合同类型列表
- `GET /v1/coins/mo` — 数币列表
- `GET /v1/coins/nets` — 数币网络（Chain）列表

### 业务配置 (5 个端点)
- `GET /v1/biz_lines` — 业务线列表
- `GET /v1/biz_lines/keyword` — 业务线名称列表（ID 查名称，全量）
- `GET /v1/activity` — 行为列表
- `GET /v1/activity/{id}` — 行为详情
- `GET /v1/behavior/label` — 行为名称列表（ID 查名称）

## references 映射表

| 用户需求 | 加载文档 |
|---------|---------|
| 银行账户 | `references/accounts-bank.md` |
| 法币账户（公司/客户/员工/供应商） | `references/accounts-fiat.md` |
| 数币账户、白名单账户、地址标签 | `references/accounts-digital-coin.md` |
| 主体（公司） | `references/master-data-company.md` |
| 客户 | `references/master-data-customer.md` |
| 项目 | `references/master-data-project.md` |
| 用户、部门 | `references/master-data-user.md` |
| 合同、数字货币、国家 | `references/master-data-contract.md` |
| 业务线、行为 | `references/business-config-biz-activity.md` |

## 注意事项

1. **分页**：每次请求 `page_size` 最大建议 100（单页上限，非总量上限）；用户要求全部数据时自动连续翻页直到取完，不得中途询问用户
2. **认证**：armada MCP（`armada__armada_get/post`）自动处理登录、token 刷新、TOTP，Agent 无需关心
3. **路径白名单**：MCP server 内置白名单，严禁凭经验猜测路径
4. **keyword / label 接口**：返回全量 id+name 列表，不支持过滤，用于 ID→名称映射
5. **唯一合法入口**：所有 armada 调用必须经父 skill 的 wrapper；wrapper 对首参 uid 做格式校验（`^U[A-Z0-9]{8,}$`），缺失或格式错误时 `exit ≠ 0`，按 Step 0 固定话术回复

## 本 skill 的引用路径

```
skills/common-ns-masterdata/
├── SKILL.md                              # 本文件
├── CLAUDE.md                             # 编辑硬约束（与父 byte-equal）
└── references/
    ├── accounts-bank.md
    ├── accounts-fiat.md
    ├── accounts-digital-coin.md
    ├── business-config-biz-activity.md
    ├── master-data-company.md
    ├── master-data-contract.md
    ├── master-data-customer.md
    ├── master-data-project.md
    └── master-data-user.md

# 依赖父 skill（不在本目录内）
skills/common-ns-system-query/
├── scripts/ns-call.sh                    # wrapper 单例
├── references/common-conventions.md
├── references/common-id-mapping.md       # 11 个字典接口
├── references/common-query-chains.md     # 6 条查询链（本域用链 #5、#6）
└── references/wrapper-caveats.md
```
