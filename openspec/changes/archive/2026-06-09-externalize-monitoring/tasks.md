> 删除类 chore(外置自建监控)。纪律:删除后既有测试**保持全绿**(以"无新增失败"为准);删表迁移**可逆往返**;拆线后**server 启动/路由无回归**。

## 1. 删除 4 张监控表(append-only down 迁移)

- [x] 1.1 写迁移测试(`tests/integration/`):空库 `alembic upgrade head` 后断言 schema **不含** `alert_rules`/`alerts`/`metric_samples`/`maintenance_windows`。先见红。
- [x] 1.2 新增 Alembic 迁移(不改 024):`upgrade()` drop 四表;`downgrade()` 按 024 列定义重建。见绿。
- [x] 1.3 可逆性:空库 `upgrade head` → `downgrade -1` → `upgrade head` 往返干净通过。

## 2. 删除 resource_monitoring 模块

- [x] 2.1 删除 `src/fleetent/platform/resource_monitoring/`(`collectors.py`/`alerting.py`/`monitoring_store.py`/`monitor_admin_api.py`/`__init__.py` + `__pycache__`)。
- [x] 2.2 `grep -rn "resource_monitoring\|monitoring_store\|collect_once" src` 确认无残留引用(server.py 见 task 3)。

## 3. 拆除 server.py 监控接线

- [x] 3.1 移除 `src/fleetent/server.py`:L50 import、L194 周期任务注册、L223 `monitor_admin_api.router` include、L378-392 `_run_monitoring_cycle()` 函数。
- [x] 3.2 写/跑 server 启动 integration 测试:app 正常启动、`GET /health` 正常、既有 admin 路由不受影响、无 `monitoring_collect` 任务注册。

## 4. 清理测试

- [x] 4.1 删除 `tests/integration/test_monitoring_collectors.py`、`test_monitoring_store.py`、`test_monitor_admin_api.py`。
- [x] 4.2 从 `tests/unit/test_platform_admin_api_unit.py`、`test_coverage_closure_helpers.py`、`test_coverage_memory_and_platform_logic.py` 摘掉监控相关引用/断言,保持全绿。

## 5. 文档:外置说明

- [x] 5.1 在部署文档说明:fleet 指标/看板/告警外置——node_exporter/cAdvisor + Prometheus(内网自托管,数据不出网)+ Grafana 看板 + Alertmanager 告警;`/health` 与 observability trace 仍由平台提供。

## 6. 收尾验证

- [x] 6.1 `make test-pr` 全绿。
- [ ] 6.2 `uv run pytest tests/integration -q` 对照 main 基线**无新增失败**。
- [x] 6.3 `openspec validate externalize-monitoring` 通过。
- [x] 6.4 复核:未触及 `agent-resource-isolation`/`sandbox-resource-limits`、observability、`/health`、任何 agent runtime 或业务表。
