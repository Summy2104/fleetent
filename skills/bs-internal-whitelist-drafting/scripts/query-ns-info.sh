#!/bin/bash
# query-ns-info.sh — 构造 NS customers + biz_lines 两路 armada 工具调用参数
#
# fleetent 适配：沙箱内没有 mcpfast，armada 是 agent loop 发起的 MCP 工具调用
# （工具名 armada__armada_get，双下划线）。本脚本不再自己拿 armada JSON，而是
# 复用 common-ns-system-query/ns-call.sh（唯一合法入口）做 uid 校验 + _meta 注入，
# 把 customers / biz_lines 两路的 `ARMADA_CALL <tool> path=... <kv> _meta={...}`
# 各打印一行到 stdout。agent 据此【逐个】发起 armada__armada_get 工具调用拿真实
# JSON，再用 run_code 做下方「字段过滤规则」的裁剪合并。
#
# 用法:
#   query-ns-info.sh <uid> <customer_name> <business_line>
#
# 输入:
#   uid            Slack sender_id（U 开头大写字母数字串），由 caller 从 Step 0 提取后传入
#   customer_name  客户名（中文/英文皆可），按名称模糊查询 /v1/customers
#   business_line  业务线名（如 量化 / Defi），按名称模糊查询 /v1/biz_lines
#
# 输出（stdout，恰好两行 ARMADA_CALL，customers 在前 biz_lines 在后）:
#   ARMADA_CALL armada__armada_get path=/v1/customers query_params={...} _meta={"slackUserId":"U..."}
#   ARMADA_CALL armada__armada_get path=/v1/biz_lines  query_params={...} _meta={"slackUserId":"U..."}
#
# agent 据此发起两次 armada__armada_get 工具调用，把两个 JSON 结果喂回 run_code 按
# 下方规则裁剪合并为：
#   {
#     "customers": [{"name": "...", "email": ["...", ...]}, ...],
#     "biz_lines": [{"name": "...", "email_group": ["...", ...]}, ...]
#   }
#
# 字段过滤规则（agent 在 run_code 里对两路 JSON 各自执行）:
#   - 只取 list[]，丢弃 page_info / total
#   - customers 每条只保留 name + email 数组；biz_lines 每条只保留 name + email_group 数组
#   - email / email_group 数组中的 null 和空字符串过滤掉（NS 返回 [""] 等同于 [] 处理）
#
# 错误（stderr + exit !=0）:
#   - 参数缺失 / uid 鉴权失败 / method 非法 → 由底层 ns-call.sh 抛出对应 exit code
#   - 任一路 ns-call.sh 失败 → 整体 exit 1，stderr 标注哪一路异常

set -euo pipefail

UID_="${1:?usage: query-ns-info.sh <uid> <customer_name> <business_line>}"
CUSTOMER_NAME="${2:?usage: query-ns-info.sh <uid> <customer_name> <business_line>}"
BUSINESS_LINE="${3:?usage: query-ns-info.sh <uid> <customer_name> <business_line>}"

NS_CALL="${SKILLS_DIR:?SKILLS_DIR not set}/common-ns-system-query/scripts/ns-call.sh"

CUST_RC=0
bash "$NS_CALL" "$UID_" get "/v1/customers" \
  "query_params={\"page\":1,\"page_size\":20,\"name\":\"$CUSTOMER_NAME\"}" || CUST_RC=$?

BIZ_RC=0
bash "$NS_CALL" "$UID_" get "/v1/biz_lines" \
  "query_params={\"page\":1,\"page_size\":10,\"name\":\"$BUSINESS_LINE\"}" || BIZ_RC=$?

if [ "$CUST_RC" -ne 0 ] || [ "$BIZ_RC" -ne 0 ]; then
  echo "ERR_NS_CALL: customers_rc=$CUST_RC biz_lines_rc=$BIZ_RC" >&2
  exit 1
fi
