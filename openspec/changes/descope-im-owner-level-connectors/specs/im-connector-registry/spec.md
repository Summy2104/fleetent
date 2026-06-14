# im-connector-registry Delta

## REMOVED Requirements

### Requirement: Connector registry storage
**Reason**: owner-level IM connector 机制 descope——`im_connectors` 表所属机制空转（ConnectorManager factories={}、无适配器），整套移除。
### Requirement: Connector status reporting
**Reason**: 同上，机制移除。
### Requirement: Runtime enable and disable
**Reason**: 同上，无连接器可启停。
### Requirement: Unconfigured connectors are not started
**Reason**: 同上，机制移除。
### Requirement: Connector listing exposes status
**Reason**: 同上，机制移除。
### Requirement: Create a connector for a not-yet-configured platform
**Reason**: 同上，机制移除。
### Requirement: Slack and Telegram are excluded from the owner-level connector lifecycle
**Reason**: owner-level lifecycle 整体移除；slack/telegram 走 per-agent（不受影响），此"排除"声明随机制消失。
