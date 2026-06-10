## Why

`session_lock()` 为每个 session 创建 `{session_id}.lock` flock 锚文件，解锁时只释放锁、不删除文件（删除有竞态风险，设计如此）。但 TTL 维护清理（`cleanup_expired()`）删除过期 session 时只连带删除 `.pre-compact.json` / `.tool_outputs/` / `.resume` / `.todo`，漏了 `.lock`——导致 session 过期删除后 `.lock` 文件成为孤儿，永久残留在 sessions 目录中，累积为磁盘垃圾并造成运维困惑（看似所有 session 都"被锁"）。

## What Changes

- `cleanup_expired()` 成功删除 session 主文件后，连带删除对应的 `{session_id}.lock` 文件（若存在），删除失败静默处理——与现有 `.pre-compact.json` / `.resume` / `.todo` 附属文件的处理方式一致
- 清理扫描遇到 `.lock` 文件本身不纳入 TTL 过期判定（现有扫描只匹配 `*.json`，天然跳过，无需改动，仅在 spec 中明确）

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `session-ttl-cleanup`: 「过期 session 一次性清理」requirement 的连带删除清单中增加 `{session_id}.lock` flock 锚文件（若存在，删除失败静默处理）

## Impact

- 受影响代码：`src/fleetent/session/manager.py` 的 `cleanup_expired()`（清理列表补一行）
- 受影响测试：`tests/integration/` 下 session 清理相关测试新增 `.lock` 连带删除用例
- 无 API / schema / 依赖变更；纯 agent 侧文件清理行为补全
