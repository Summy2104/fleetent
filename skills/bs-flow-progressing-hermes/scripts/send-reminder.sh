#!/bin/bash
set -euo pipefail

# send-reminder.sh — 拼接催办消息模板，输出到 stdout，由 agent 调用内置 send_im_message 发送
#
# 用法：
#   send-reminder.sh <uid> <kv...>
#
# 必填 kv：
#   mongo_id=<string>
#   process_no=<string>
#   email_subject=<string>
#   waiting_time=<string>        # 如 "1天"、"3小时"
#   task_name=<string>
#   starter_name=<string>
#   sender_slack_id=<string>     # 催办人 Slack ID（U 开头），用于收到回应回查
#
# 可选 kv：
#   overdue_hours=<int>          # 默认 0，>0 时追加"超 SLA"
#   last_actor=<string>          # 有值才输出"上一步"行
#   last_action=<string>         # 配合 last_actor
#   last_comment=<string>        # 有值才追加括号内意见
#   remaining_chain=<string>     # 后续审批链，如 "财务审批 → BOSS审批"
#   n_remaining=<int>            # 0=最终节点，>0=输出 remaining_chain

_UID="${1:?usage: send-reminder.sh <uid> [kv...]}"
shift 1

# 解析 kv 参数
mongo_id=""
process_no=""
email_subject=""
waiting_time=""
task_name=""
starter_name=""
sender_slack_id=""
overdue_hours=0
last_actor=""
last_action=""
last_comment=""
remaining_chain=""
n_remaining=-1

valid_keys="mongo_id process_no email_subject waiting_time task_name starter_name sender_slack_id overdue_hours last_actor last_action last_comment remaining_chain n_remaining"

for arg in "$@"; do
  key="${arg%%=*}"
  val="${arg#*=}"
  # 校验参数名合法性
  if ! echo " $valid_keys " | grep -q " $key "; then
    echo "ERR: unknown parameter '$key'. Valid parameters: $valid_keys. Please re-run with correct parameter names." >&2
    exit 2
  fi
  case "$key" in
    mongo_id)        mongo_id="$val" ;;
    process_no)      process_no="$val" ;;
    email_subject)   email_subject="$val" ;;
    waiting_time)    waiting_time="$val" ;;
    task_name)       task_name="$val" ;;
    starter_name)    starter_name="$val" ;;
    sender_slack_id) sender_slack_id="$val" ;;
    overdue_hours)   overdue_hours="$val" ;;
    last_actor)      last_actor="$val" ;;
    last_action)     last_action="$val" ;;
    last_comment)    last_comment="$val" ;;
    remaining_chain) remaining_chain="$val" ;;
    n_remaining)     n_remaining="$val" ;;
  esac
done

# 校验必填
for field in mongo_id process_no email_subject waiting_time task_name starter_name sender_slack_id; do
  eval "val=\$$field"
  [ -n "$val" ] || { echo "ERR: missing required field: $field" >&2; exit 1; }
done

# 拼接超时段
overdue_seg=""
if [ "$overdue_hours" -gt 0 ] 2>/dev/null; then
  overdue_seg="（超 SLA ${overdue_hours}h）"
fi

# 拼接上一步行
prev_line=""
if [ -n "$last_actor" ] && [ -n "$last_action" ]; then
  comment_seg=""
  [ -n "$last_comment" ] && comment_seg="（${last_comment}）"
  prev_line="📝 上一步：${last_actor} 已${last_action}${comment_seg}"
fi

# 拼接后续审批行
chain_line=""
if [ "$n_remaining" -eq 0 ] 2>/dev/null; then
  chain_line="🏁 本节点为最终节点"
elif [ "$n_remaining" -gt 0 ] 2>/dev/null && [ -n "$remaining_chain" ]; then
  chain_line="🪜 后续审批：${remaining_chain}（共 ${n_remaining} 级）"
fi

# 拼接完整消息
URL="https://admin.nsdigital.io/approval/flow/view?id=${mongo_id}&no=${process_no}&version=v2"

MSG="🔔 审批提醒

📄 ${email_subject}（${process_no}）
🔗 立即处理：${URL}

⏱ 已等待：${waiting_time}${overdue_seg}
🎯 当前节点：${task_name}
👤 发起人：${starter_name}
🙋 催办人：<@${sender_slack_id}>"

[ -n "$prev_line" ]  && MSG="${MSG}
${prev_line}"
[ -n "$chain_line" ] && MSG="${MSG}
${chain_line}"

MSG="${MSG}

✅ 请在本消息列下回复，我会自动通知催办人：
  1️⃣  收到（已收到，正在处理）
  2️⃣  已完成（已在 NS 系统中审批）

或回复 \`收到\` / \`收到 ${process_no}\` 也可识别
—— 本消息由 BS Assistant 自动发送"

[[ "$_UID" =~ ^U[A-Z0-9]{8,}$ ]] || { echo "ERR_AUTH_INVALID" >&2; exit 3; }

echo "$MSG"
