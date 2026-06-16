#!/usr/bin/env bash
# run_email_sync.sh — 邮件模版批量同步启动脚本
#
# 用法：
#   bash run_email_sync.sh
#
# Cron 示例：
#   0 2 * * * bash /path/to/run_email_sync.sh >> /var/log/email-sync.log 2>&1

set -euo pipefail

# ── 环境变量配置 ───────────────────────────────────────────────────────────────

# HOST_MEDIA_DIR：当前 agent 的 host-side media 目录（per-agent）。
#   fleetent: <FLEETENT_HOME>/<agent>/media
export AGENT_ID="bs-intern"
export FLEETENT_HOME="${FLEETENT_HOME:-$HOME/.fleetent}"
export HOST_MEDIA_DIR="$FLEETENT_HOME/$AGENT_ID/media"
export SLACK_NOTIFY_CHANNEL="C0XXXXXXXXX"   # 替换为实际 Slack 频道 ID

# ── 执行 Python 编排脚本 ────────────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/orchestrate_email_sync.py"
