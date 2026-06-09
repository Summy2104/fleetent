## REMOVED Requirements

### Requirement: Four-layer resource metrics collection
**Reason**: 自建采集(host/process/container/infra)是 Prometheus 生态的弱重造,整体外置。
**Migration**: node_exporter(host/process)+ cAdvisor(container)+ 各组件 exporter(infra),Prometheus 抓取。

### Requirement: Collector self-failure is surfaced, never silently dropped
**Reason**: 同上。
**Migration**: Prometheus `up` 指标 + scrape 失败告警替代采集中断告警。

### Requirement: Real-time dashboard and history curves
**Reason**: 同上,看板外置。
**Migration**: Grafana 仪表盘(实时 + 历史曲线),Prometheus 作 TSDB(真正的保留/降采样)。

### Requirement: Collection and storage stay within the internal network
**Reason**: 同上。数据主权不变——Prometheus/Grafana 均自托管、内网部署。
**Migration**: 内网自托管 Prometheus + Grafana,数据不出内网。

### Requirement: Monitoring dashboard is read-only for viewers
**Reason**: 同上,看板权限外置。
**Migration**: Grafana 的 Viewer 角色(只读)。
