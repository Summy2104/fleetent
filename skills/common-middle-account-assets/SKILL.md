---
name: common-middle-account-assets
description: >
  **Internal — 由 common-middle-system-query 路由调用，不应被独立触发**。
  中台账户/子账户**资产快照**查询（middle-mcp `balance_get_account_balance` 接口）。
  按账户名（含邮箱形态）/ 名称列表 / 范围（前缀+数字区间）拉取当前可用 / 冻结资产，
  输出 xlsx 汇总附件 + USDT 估值文字。
  **Do NOT use for**: 按 UID 查账户（本工具只接受 name / account_id，不接受 uid；
  按 UID 查走 common-middle-accounts.account_list_accounts.uid）；账户主数据
  （类型/状态/启用）查询（→ common-middle-accounts）；动账流水（→ bs-transaction-history）；
  CEX 母账户费率（→ bs-exchange-rate）。仅当上游 hub 路由进入本 skill 时生效。
status: active
metadata:
  author: RD Team
  version: 2.0.0
complexity: L1
---

# 中台账户子账户资产查询

> ⛔ **执行前强制约束**
> 1. 必须读完本文档再执行；不得凭记忆猜测参数。
> 2. 所有业务逻辑由 `fetch-assets.py` 完成（经 `run_code` 在沙箱内执行），SKILL 只做编排。
> 3. 严禁直接拼 HTTP / curl 绕过中台 MCP 工具。
> 4. 严禁对脚本输出追加任何内容或总结。
> 5. 严禁将脚本返回的内部文件路径直接暴露给用户。
> 6. 已通过 `send_file` 发送的文件只发送一次，不得重复发送。

> NOTE (fleetent): 本 skill 经 `fetch-assets.py` shell-out 调用中台 `middle__balance_get_account_balance`。fleetent 里 MCP 工具是 agent 循环里的直接调用，不在 run_code 沙箱内通过 CLI 发起；hub 的 `middle-call.sh` 当前是占位、未对接中台访问桥接（调用以 exit 3 返回）。另：中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内。下文流程、参数、输出契约均保留作为参考。

**环境变量**（沙盒内）：

| 变量 | 来源 | 说明 |
|------|------|------|
| `SKILLS_DIR` | 沙箱注入 | skills 根目录（用于定位 hub wrapper 脚本） |
| `OUTBOUND_DIR` | sandbox | 输出文件目录；未设置则回退 `/tmp` |

## Step 1 — 解析用户输入（LLM 层）

将用户输入标准化为以下两种格式之一：

**格式 A — 名称列表：**
```json
["Alice", "Bob", "ZYJDW00203-B5"]
```

**格式 B — 范围（前缀 + 数字区间）：**
```json
{"prefix": "ZYJDW00203-B", "start": 1, "end": 79, "pad_width": 0}
```

> `pad_width`：数字前导零位数。`B01` 对应 2，`B1` 对应 0。

**范围识别规则：**
- 支持连接词：`到` / `一直到` / `to` / `~`
- 前缀可省略第二次（「B1 到 B79」与「ZYJDW-B1 到 ZYJDW-B79」均合法）
- 展开后数量 > 100：回复用户「展开后共 N 个账户，请确认后再次发送」，**不调用脚本**

**名称为空：** 提示用户提供账户名称，不调用脚本。

## Step 2 — 调用脚本（经 `run_code` 在沙箱内执行）

```bash
# 列表模式
python3 $SKILLS_DIR/common-middle-account-assets/scripts/fetch-assets.py \
  --names '["Alice","Bob"]'

# 范围模式
python3 $SKILLS_DIR/common-middle-account-assets/scripts/fetch-assets.py \
  --range '{"prefix":"ZYJDW00203-B","start":1,"end":79,"pad_width":0}'
```

## Step 3 — 解析 stdout 并响应

| stdout 包含 | 动作 |
|------------|------|
| `账户资金汇总：` 开头的行 | 直接回复用户（原样输出这些行） |
| `已生成 Excel 文件：<path>` | 提取路径，用 `send_file` 把文件发回当前对话 |
| `账户 X 查询失败：` | 回复用户该错误信息 |
| `（无资产数据）` | 直接回复用户 |
| `展开后共` 开头的行 | 原样回复用户该确认提示，等待用户确认后重新发送 |
| 脚本 exit 非 0 | 回复「查询失败，请稍后重试」 |

发送文件：用 `send_file(path="<脚本输出的完整路径>")` 把 `.xlsx` 发回当前对话（向用户呈现为 `account-assets.xlsx`）。

## Step 4 — 清理文件（经 `run_code`）

```bash
rm -f <发送的文件路径>
```

## 不做（边界）

- 不接受 `account_id` 或 `code` 直接输入
- 不做估值口径转换（USD → CNY/HKD 等法币换算）
- 不做 P&L 趋势分析
- 不做交易记录 / 流水

## 引用路径

```
skills/common-middle-account-assets/
├── SKILL.md              # 本文件（编排）
├── SKILL.tests.yaml      # 测试用例
└── scripts/
    ├── fetch-assets.py   # 唯一业务脚本
    └── test_fetch_assets.py  # 单元测试
```
