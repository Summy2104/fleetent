## REMOVED Requirements

### Requirement: Threshold plus duration alert rules
**Reason**: 自建告警随 fleet 监控整体外置到 Prometheus/Alertmanager。
**Migration**: 用 Prometheus alerting rules(`expr` + `for` 持续时间)定义阈值+持续告警。

### Requirement: Rule enable, disable, and clone
**Reason**: 同上,规则管理外置。
**Migration**: Prometheus rule 文件 + 版本控制管理启停/克隆。

### Requirement: Static threshold and optional rate-of-change rules
**Reason**: 同上。
**Migration**: Prometheus 表达式(静态阈值 / `rate()`/`delta()` 速率)替代。

### Requirement: Rule management is admin-only
**Reason**: 同上,规则不再由本平台管理。
**Migration**: 由运维通过 Prometheus 配置 + RBAC 管控。
