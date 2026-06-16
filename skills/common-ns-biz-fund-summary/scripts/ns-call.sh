#!/bin/bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# 统一参数位置（不论是否 bypass）：<uid> <method> <path> [kv...]
#
# uid 作为首参由 agent 在每次调用时传入（来源：SKILL.md Step 0
# 用内置 whoami 取得的 sender_id）。不再使用任何共享文件/env —
# 每次调用的进程边界即是状态边界。
#
# server 名来自部署期注入的 $ARMADA_MCP_SERVER（per-agent 模式）。
# 兼容性：env 未设置时回退 armada-v2-mcp（旧全局名）。
#
# NOTE (fleetent): fleetent 沙箱内无 `mcpfast` CLI——armada 是 fleetent 挂载的
#   MCP server，调用形式为模型直接工具调用 `armada__armada_get` /
#   `armada__armada_post`（path 作为参数，`_meta={"slackUserId": <uid>}` 随同传入）。
#   本 wrapper 承载的「校验 uid 格式 + 注入 _meta.slackUserId + 装配 path/参数」契约
#   在 fleetent 下等价于：先用 whoami 取 sender_id，再以该 uid 组 _meta 调用
#   对应的 `armada__armada_<method>` 工具。下方 `mcpfast` 调用行保留以表达参数
#   装配契约（OpenClaw/Hermes 运行时遗留），fleetent 下由模型按上述映射直接调用工具。
# ──────────────────────────────────────────────────────────────

_UID="${1:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
METHOD="${2:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
REQ_PATH="${3:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
shift 3

_ARMADA_SERVER="${ARMADA_MCP_SERVER:-armada-v2-mcp}"

# 紧急降级开关（仅运维手动启用）：跳过鉴权 + _meta 注入，裸透传
if [ -n "${NS_CALL_BYPASS:-}" ]; then
  echo "⚠️ NS_CALL_BYPASS=1, bypassing _meta injection (uid='$_UID' ignored)" >&2
  exec mcpfast "${_ARMADA_SERVER}.armada_${METHOD}" path="$REQ_PATH" "$@"
fi

SLACK_UID="$_UID"
[[ "$SLACK_UID" =~ ^U[A-Z0-9]{8,}$ ]] || { echo "ERR_AUTH_INVALID" >&2; exit 3; }

case "$METHOD" in
  get|post) ;;
  *) echo "ERR_METHOD_INVALID: $METHOD" >&2; exit 4 ;;
esac

for arg in "$@"; do
  case "$arg" in
    _meta=*) echo "ERR_META_DUPLICATE" >&2; exit 5 ;;
  esac
done

exec mcpfast "${_ARMADA_SERVER}.armada_${METHOD}" \
  path="$REQ_PATH" \
  "$@" \
  "_meta={\"slackUserId\":\"$SLACK_UID\"}"
