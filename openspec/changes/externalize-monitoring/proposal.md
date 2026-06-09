## Why

自建 fleet 监控经核实是**通用基础设施指标的弱重造**:`collectors.py` 用 stdlib 采 host CPU/内存、process、container、infra 四层,写进 `metric_samples`(SQLite 当时序库——无保留/降采样/高效范围查询),配 `alert_rules`/`alerts`/`maintenance_windows` + admin 看板。这些正是 **Prometheus + node_exporter/cAdvisor + Grafana + Alertmanager** 原生且更强的领域,且这套全可自托管、符合数据主权。

移除自建、外置,缩小实体集与维护面。**`/health`(liveness)与 observability trace(agent 域遥测)是另一回事,保留不动。**

## What Changes

- **删除** `resource_monitoring` 模块(collectors / alerting / monitoring_store / monitor_admin_api）。
- **删除 4 表** `alert_rules` / `alerts` / `metric_samples` / `maintenance_windows`：新增 append-only down 迁移(不回退 024）。
- **移除 server.py 监控接线**：import、周期任务注册、`monitor_admin_api` router、`_run_monitoring_cycle()`。
- **外置(文档化,不写新代码)**：fleet 指标/看板/告警交由客户自托管 Prometheus/Grafana/Alertmanager；主机/容器指标用 node_exporter/cAdvisor 抓。**本次不新增 `/metrics` 端点**——若将来需要导出 app 域指标,另起一个 additive change。
- **保留**：`GET /health`、observability trace;以及 `agent-resource-isolation` / `sandbox-resource-limits`(沙箱/agent 资源限额,与 fleet 监控无关)。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
（无）

### Removed Capabilities
整体移除以下 5 个 capability(各 spec 的全部 requirements 经 REMOVED delta 退场,迁移指向外置 Prometheus 栈)：
- `alert-rules`
- `alert-lifecycle`
- `alert-notification-channels`
- `resource-metrics-collection`
- `monitoring-admin-ui`

## Impact

- **模块(删)**：`src/fleetent/platform/resource_monitoring/`(`collectors.py`/`alerting.py`/`monitoring_store.py`/`monitor_admin_api.py`/`__init__.py`)。
- **迁移**：新增 down 迁移 drop 4 表(逆 `024_add_monitoring_tables.py`)。
- **接线(改)**：`src/fleetent/server.py`(L50 import、L194 周期任务、L223 router、L378-392 `_run_monitoring_cycle`）。`cron_scheduler.register_interval_job` 是通用机制,不动。
- **specs(移除)**：上列 5 个。
- **测试**：删 `tests/integration/test_monitoring_{collectors,store}.py`、`test_monitor_admin_api.py`；改 `tests/unit/test_platform_admin_api_unit.py`、`test_coverage_closure_helpers.py`、`test_coverage_memory_and_platform_logic.py`(摘掉监控引用)。
- **零影响**：agent runtime、DB runtime、任何业务表;数据主权不变(Prometheus 自托管)。
