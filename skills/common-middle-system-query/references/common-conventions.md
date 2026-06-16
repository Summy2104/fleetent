# 中台查询共通规范

供 `common-middle-system-query` 及其子 skill (`common-middle-account-assets` / `bs-exchange-rate` / `bs-transaction-history`) 共同遵守。

## 1. 数值精度

中台返回金额 / 余额 / 汇率字段，**严禁**任何形式的格式化加工：

| 禁止 | 允许 |
|------|------|
| `round(value, 2)` | 原字面 |
| `float(value)` / `int(value)` | 字符串透传 |
| 千分位 `f"{x:,.2f}"` | 原字面 |
| 单位换算 USD → CNY/HKD | 不做 |
| 拼接百分号 / 货币符号 | 不做（除非中台返回里本就含） |

Python 脚本读 JSON 必须用 `json.loads(text, parse_float=str)` 锁字面，避免 IEEE 754 损精度。

## 2. 字段展示

- 中台返回 JSON 字段名为英文（`account_code` / `currency` / `balance_available` 等）
- 子 skill 必须按自己的 references 字段映射表展示**中文列名**
- **没有中文映射的字段不展示**，不要硬翻译猜测
- 嵌套对象 / 数组按同规则逐层展开

## 3. 时间格式

| 场景 | 时区 | 格式 |
|------|------|------|
| 大部分接口 `updated_at` / `created_at` | UTC → UTC+8 | `YYYY-MM-DD HH:mm:ss` |
| `transaction_list_account_transactions` V2 的 `date` 字段 | **保留 UTC+0**（接口本就是 UTC+0） | `YYYY-MM-DD HH:mm:ss` |

⚠️ 注意 `bs-transaction-history` 是例外，详见该 skill 自身 SKILL.md。

## 4. 文件交付

- xlsx 等输出文件**必须**通过 `send_file` 发回当前对话
- **严禁**回复中暴露内部文件路径（`/tmp/...` 字面）
- **空结果**（rows=0）仍交付只有表头的 xlsx，正确话术示例：
  > 区间内无动账流水（account_id=1204, 时间 2026-04-29 ~ 2026-05-19）。空表头文件已附上。（同时用 `send_file` 发回该文件）
- **已发送的文件只发送一次**，不要重复发送

## 5. 服务名约定

中台 MCP 工具以 `middle__<tool_name>` 直接调用。`X-API-Key` 由 `middle` MCP server 自身配置注入；per-agent 的 `middle` server 配置决定该 agent 能访问的数据权限范围。spoke 不接触 server 名字面值或 Token。

> NOTE (fleetent): `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内，运行前需在 my-bot 挂载。

## 6. 输出列固定布局

涉及 xlsx 输出的子 skill（目前仅 `bs-transaction-history`），列布局必须**写死在脚本里**（`scripts/render_xlsx.py:COLUMNS`），agent 不得自行增删列。新增列需走脚本改 PR。
