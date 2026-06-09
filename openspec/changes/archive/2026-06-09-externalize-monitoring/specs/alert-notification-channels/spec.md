## REMOVED Requirements

### Requirement: Per-rule multi-channel notification
**Reason**: 通知投递随 fleet 监控外置。
**Migration**: Alertmanager receivers + routing(按 rule/label 路由到多渠道)。

### Requirement: Webhook outbound to external systems
**Reason**: 同上。
**Migration**: Alertmanager webhook receiver。

### Requirement: Send failure retry and failure record
**Reason**: 同上。
**Migration**: Alertmanager 内建重试 + 其 metrics/日志记录失败。
