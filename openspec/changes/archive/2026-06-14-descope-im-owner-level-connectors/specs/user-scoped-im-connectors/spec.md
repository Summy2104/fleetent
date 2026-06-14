# user-scoped-im-connectors Delta

## REMOVED Requirements

### Requirement: Per-owner connector registry
**Reason**: owner-level IM connector 机制整体 descope（owner→tenant 塌缩第三刀）。
### Requirement: Owner-scoped credential resolution with admin-only env fallback
**Reason**: 同上。
### Requirement: Per-owner adapter lifecycle
**Reason**: 同上，机制空转、无适配器。
### Requirement: Owner-isolated inbound routing
**Reason**: 同上；per-agent slack/telegram 路由由连接=agent 决定，不经此。
### Requirement: Owner-scoped IM identity and allowlist
**Reason**: 身份已在阶段 3b 瘦身（im_users 删 owner_id）、allowlist 已 descope；owner 作用域退役。
### Requirement: Admin sees and manages all owners
**Reason**: owner 概念在 IM 域退役。
### Requirement: Admin UI shows owner scope
**Reason**: 同上。
### Requirement: Backward-compatible migration to admin owner
**Reason**: owner→tenant 塌缩，owner 概念移除，迁移目标作废。
