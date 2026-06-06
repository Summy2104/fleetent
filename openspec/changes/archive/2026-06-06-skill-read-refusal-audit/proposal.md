## Why

`skill-injection-audit` spec 要求 `read_skill` 对 `audit_blocked` skill 返回拒绝文本时记录审计日志，但 `builtin_tools.read_skill()` 只返回拒绝文本、不写日志。安全审计无法发现"agent 被（误）导向一个被封禁 skill"的尝试——被拒事件不留痕迹。

## What Changes

- `read_skill()` 在 `audit_blocked` 拒绝分支写一条审计日志（`audit_log.write_audit`，action `skill.read_refused`，target skill 名，detail 含原因）
- `read_skill()` opt-in `tool_context` 参数，把可得的 `session_id` / `agent_name` 记入审计 detail（便于溯源）

## Capabilities

### New Capabilities

无新 capability。

### Modified Capabilities

- `skill-injection-audit`：明确 `read_skill` 对 audit_blocked skill 拒绝时 MUST 写审计日志

## Impact

- **修改文件**：`src/fleetent/tools/builtin_tools.py`（`read_skill`）
- **依赖**：`governance.audit_log.write_audit`（已存在；经 user_store DB，standalone 可访问）
- **测试**：`tests/unit/`（验证拒绝时写日志、正常读取不写、含 session/agent 上下文）
- **无破坏性变更**：仅在 audit_blocked 拒绝分支新增日志；正常读取路径不变；`read_skill` 新增可选 `tool_context` 参数不影响 LLM schema（out-of-band 注入）
