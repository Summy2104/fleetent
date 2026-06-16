#!/bin/bash
set -euo pipefail
# fleetent 适配：armada 是直接 MCP 工具调用，工具名 = armada__armada_<method>（双下划线）。
# 本 wrapper 是唯一合法入口：校验 uid 格式 + 构造 _meta.slackUserId，
# 把要传给 armada 工具的最终参数打印到 stdout，供 agent 据此发起 MCP 调用。
_UID="${1:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
METHOD="${2:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
REQ_PATH="${3:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
shift 3
_ARMADA_TOOL="armada__armada_${METHOD}"
if [ -n "${NS_CALL_BYPASS:-}" ]; then
  echo "⚠️ NS_CALL_BYPASS=1, bypassing _meta injection (uid='$_UID' ignored)" >&2
  echo "ARMADA_CALL ${_ARMADA_TOOL} path=$REQ_PATH $*"
  exit 0
fi
SLACK_UID="$_UID"
[[ "$SLACK_UID" =~ ^U[A-Z0-9]{8,}$ ]] || { echo "ERR_AUTH_INVALID" >&2; exit 3; }
case "$METHOD" in get|post) ;; *) echo "ERR_METHOD_INVALID: $METHOD" >&2; exit 4 ;; esac
for arg in "$@"; do case "$arg" in _meta=*) echo "ERR_META_DUPLICATE" >&2; exit 5 ;; esac; done
echo "ARMADA_CALL ${_ARMADA_TOOL} path=$REQ_PATH $* _meta={\"slackUserId\":\"$SLACK_UID\"}"
