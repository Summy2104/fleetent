## REMOVED Requirements

### Requirement: Alert lifecycle state machine
**Reason**: 告警生命周期随 fleet 监控外置。
**Migration**: Alertmanager 的 firing/resolved 状态机 + Grafana 告警中心。

### Requirement: Critical alert escalation when unacknowledged
**Reason**: 同上。
**Migration**: Alertmanager `repeat_interval` + 路由升级(routing tree)。

### Requirement: Deduplication, aggregation, grouping, and inhibition
**Reason**: 同上。
**Migration**: Alertmanager 原生 dedup / grouping / inhibition rules。

### Requirement: Maintenance window silencing
**Reason**: 同上。
**Migration**: Alertmanager silences(按时间窗静默)。

### Requirement: Alert center search, snapshot, and audit
**Reason**: 同上。
**Migration**: Grafana / Alertmanager UI 检索 + 其自带审计;平台仅保留 observability trace。
