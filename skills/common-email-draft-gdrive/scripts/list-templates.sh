#!/usr/bin/env bash
set -euo pipefail

# NOTE (fleetent): 本脚本原通过 `mcpfast` 在 shell 内调用 Google Drive MCP；
# fleetent 的 MCP 工具是模型层直接工具调用，无法从 shell 脚本发起。
# 列模板请改为直接调用 `google-drive__listFolder`（详见 SKILL.md Step 1），本脚本不再使用。

# 校验必要环境变量
if [ -z "${GDRIVE_EMAIL_TEMPLATE_FOLDER:-}" ]; then
  echo "[ERROR] 环境变量 GDRIVE_EMAIL_TEMPLATE_FOLDER 未设置" >&2
  exit 1
fi

# TEMPLATES 每行格式：<name>|<file_id>
TEMPLATES=""
PAGE_TOKEN=""

while true; do
  if [ -z "$PAGE_TOKEN" ]; then
    RESULT=$(mcpfast "${GOOGLE_DRIVE_MCP_SERVER}.listFolder" "folderId=${GDRIVE_EMAIL_TEMPLATE_FOLDER}" 2>&1) || {
      echo "[ERROR] GDrive 连接失败，请检查 mcporter daemon 状态：systemctl status mcporter-daemon" >&2
      exit 3
    }
  else
    RESULT=$(mcpfast "${GOOGLE_DRIVE_MCP_SERVER}.listFolder" "folderId=${GDRIVE_EMAIL_TEMPLATE_FOLDER}" "pageToken=${PAGE_TOKEN}" 2>&1) || {
      echo "[ERROR] GDrive 分页请求失败" >&2
      exit 3
    }
  fi

  # mcpfast 返回纯文本，每行格式：📄 <filename>-AI (ID: <file_id>)
  while IFS= read -r line; do
    name=$(echo "$line" | sed 's/^📄 //' | sed 's/-AI (ID:.*//')
    file_id=$(echo "$line" | sed 's/.*ID: \([^)]*\)).*/\1/')
    TEMPLATES="${TEMPLATES}${name}|${file_id}"$'\n'
  done < <(echo "$RESULT" | grep -E '\-AI \(ID:' || true)

  PAGE_TOKEN=$(echo "$RESULT" | grep "^More items available. Use pageToken:" | sed 's/More items available. Use pageToken: //') || true
  [ -z "$PAGE_TOKEN" ] && break
done

COUNT=$(echo "$TEMPLATES" | grep -c '[^[:space:]]' || echo "0")
if [ "$COUNT" -eq 0 ]; then
  echo "[ERROR] 未找到任何邮件模板，请检查 GDRIVE_EMAIL_TEMPLATE_FOLDER 配置" >&2
  exit 4
fi

echo ""
i=1
while IFS='|' read -r name file_id; do
  [ -z "$name" ] && continue
  printf " %2d. %-50s %s\n" "$i" "$name" "$file_id"
  i=$((i+1))
done <<< "$TEMPLATES"

echo ""
printf "请输入模板编号或模板名称：\n"
