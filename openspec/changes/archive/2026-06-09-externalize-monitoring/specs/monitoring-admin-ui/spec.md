## REMOVED Requirements

### Requirement: Monitoring tab
**Reason**: 控制台监控 UI 随 fleet 监控外置。
**Migration**: Grafana 仪表盘;控制台如需可外链或内嵌 Grafana 面板。

### Requirement: Alert rules management
**Reason**: 同上。
**Migration**: Prometheus alerting rules(配置 + 版本控制),不在平台 UI 管理。

### Requirement: Alert handling
**Reason**: 同上。
**Migration**: Alertmanager / Grafana 告警处理(ack/silence)。
