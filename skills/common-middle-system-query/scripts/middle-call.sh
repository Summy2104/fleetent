#!/bin/bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# middle-call.sh — 中台 (middle) MCP 调用包装（fleetent 适配占位）
#
# NOTE (fleetent): fleetent 里 MCP 工具是 agent 循环里的直接工具调用
#   （工具名 middle__<tool_name>），不在 run_code 沙箱内通过 CLI 发起。
#   原 OpenClaw/Hermes 版本通过 `mcporter call` 从脚本内 shell-out 调用中台，
#   该机制在 fleetent 沙箱内无对应物。两种落地方式：
#     (A) 由 agent 直接调用 `middle__<tool_name>`，把结果数据交给脚本处理；
#     (B) 若必须在脚本内拉数据，需另配一个能访问中台的 HTTP/CLI 桥接，
#         并在此 wrapper 内对接（当前未实装）。
#   另：中台 `middle` MCP server 当前不在 my-bot 已挂载的 MCP 清单内。
#
# 调用契约（供 spoke 脚本沿用同一签名，桥接落地后即可工作）：
#   bash $SKILLS_DIR/common-middle-system-query/scripts/middle-call.sh \
#        <tool_name> '<args_json>'
#
# 参数纪律（详见 common-mcp-guide）：
#   中台 OpenAPI 把 uid / account_owner / market / tag / 多值逗号串等
#   字段标为 str，其值常是纯数字字符串。args_json 里这些字段必须显式
#   带引号传字符串（如 {"uid": "123456"}），不要传成整数，否则服务端
#   返回 type error 或空结果（result: []）。
#
# Usage:
#   middle-call.sh <tool_name> '<args_json>'
#
# Examples:
#   middle-call.sh common_list_chains '{"limit": 50}'
#   middle-call.sh account_list_accounts '{"uid": "123456", "limit": 50}'
#   middle-call.sh balance_get_account_balance '{"name": "bntrad8@nsdigital.io"}'
#
# 完整工具清单（19 个）与每个工具的危险字段标注见
# references/common-tool-naming.md。
#
# Exit codes:
#   0   success
#   2   bad usage (missing tool_name 或 args_json)
#   3   未实装：fleetent 下中台 MCP 桥接尚未对接（见上文 NOTE）
# ──────────────────────────────────────────────────────────────

TOOL_NAME="${1:?usage: middle-call.sh <tool_name> '<args_json>'}"
ARGS_JSON="${2:?usage: middle-call.sh <tool_name> '<args_json>' (use '{}' for no args)}"

echo "middle-call.sh: fleetent 下中台 MCP 桥接尚未对接（tool=${TOOL_NAME}）。" >&2
echo "请由 agent 直接调用 middle__${TOOL_NAME}，或配置中台访问桥接后再用本 wrapper。" >&2
exit 3
