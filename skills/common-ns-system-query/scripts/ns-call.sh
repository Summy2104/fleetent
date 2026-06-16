#!/bin/bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────
# 统一参数位置（不论是否 bypass）：<uid> <method> <path> [kv...]
#
# uid 作为首参由 agent 在每次调用时传入（来源：SKILL.md Step 0
# 从 incoming JSON 提取的 sender_id）。不再使用任何共享文件/env —
# 每次 exec 的进程边界即是状态边界。
#
# fleetent 适配：armada 是直接的 MCP 工具调用，工具名 = armada__armada_<method>
# （双下划线，见 my-bot MCP 清单）。本 wrapper 仍是「唯一合法入口」——它做 uid
# 格式校验并构造 _meta.slackUserId，然后由 agent 用构造出的参数发起
# armada__armada_get / armada__armada_post 工具调用。
# 本脚本运行在沙箱内（用 run_code / bash_exec 调用）：校验通过后把要传给
# armada 工具的最终参数（path / kv / _meta）打印到 stdout，供 agent 据此发起 MCP 调用。
# ──────────────────────────────────────────────────────────────

_UID="${1:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
METHOD="${2:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
REQ_PATH="${3:?usage: ns-call.sh <uid> <get|post> <path> [kv...]}"
shift 3

# fleetent 工具名固定为 armada__armada_<method>（双下划线）。
_ARMADA_TOOL="armada__armada_${METHOD}"

# 紧急降级开关（仅运维手动启用）：跳过鉴权 + _meta 注入，裸透传
if [ -n "${NS_CALL_BYPASS:-}" ]; then
  echo "⚠️ NS_CALL_BYPASS=1, bypassing _meta injection (uid='$_UID' ignored)" >&2
  echo "ARMADA_CALL ${_ARMADA_TOOL} path=$REQ_PATH $*"
  exit 0
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

# 校验通过：打印 agent 应据此发起的 armada__armada_<method> 工具调用参数
# （path / 透传 kv / 注入的 _meta.slackUserId）。
echo "ARMADA_CALL ${_ARMADA_TOOL} path=$REQ_PATH $* _meta={\"slackUserId\":\"$SLACK_UID\"}"
