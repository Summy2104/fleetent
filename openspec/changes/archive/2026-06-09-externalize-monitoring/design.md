## Context

自建监控经核实(2026-06-09):`platform/resource_monitoring/` 用 stdlib 采四层 infra 指标写 `metric_samples`(SQLite-as-TSDB),配 `alert_rules`/`alerts`/`maintenance_windows` + `monitor_admin_api` 看板,由 `server.py` 周期 `_run_monitoring_cycle()` 驱动。这是 Prometheus 生态(node_exporter/cAdvisor + Prometheus + Grafana + Alertmanager,均可自托管)的弱重造。本变更移除自建、外置。

爆炸半径全在 platform 控制面 + server.py + 监控自身 specs/tests,**零 agent runtime / DB runtime / 业务表影响**。

## Goals / Non-Goals

**Goals：**
- 删除 `resource_monitoring` 模块 + 4 表 + server.py 接线 + 5 个监控 capability。
- 把 fleet 指标/看板/告警外置到客户自托管 Prometheus/Grafana/Alertmanager(文档说明)。

**Non-Goals（明确保留/排除）：**
- **保留** `GET /health`(liveness)、observability trace(agent 域遥测)——与 fleet 监控无关。
- **不碰** `agent-resource-isolation` / `sandbox-resource-limits`(沙箱/agent 资源限额,不同概念)。
- **本次不新增 `/metrics` exposition 端点**——若将来要导出 app 域指标,另起 additive change。
- 不动 `cron_scheduler.register_interval_job`(通用机制,仅被监控用过)。

## Decisions

**D1：append-only down 迁移删 4 表,不回退 024。** 新迁移 `upgrade()` drop `alert_rules`/`alerts`/`metric_samples`/`maintenance_windows`;`downgrade()` 按 024 列定义重建以保可逆。符合 persistence-hygiene 迁移卫生。

**D2：外置靠文档,不写桥接代码。** 本变更是"减法",不引入 /metrics exporter;部署文档说明用 node_exporter/cAdvisor + Prometheus + Grafana + Alertmanager。降低本期爆炸半径,避免半成品桥接。

**D3：server.py 干净拆线。** 移除 import、周期任务注册、router include、`_run_monitoring_cycle()` 函数四处;确认移除后 server 启动与既有路由不受影响。

## Risks / Trade-offs

- **[失去控制台内嵌监控视图]** → 外置后用户用 Grafana;控制台如需可后续外链/内嵌(不在本期)。
- **[数据主权担忧]** → 不变:Prometheus/Grafana 自托管、内网部署,数据不出内网。
- **[迁移可逆性]** → `downgrade()` 须能重建 4 表;空库 upgrade→downgrade→upgrade 往返通过。
- **[测试残留引用]** → 删 3 个监控 integration 测试;3 个含监控引用的 unit 测试须摘干净,跑全绿。
- **[server 启动回归]** → 拆线后跑 server 启动/health/既有 admin 路由的 integration 测试确认无回归。
