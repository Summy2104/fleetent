## Why

fleetent 已经有 structured logs、SQLite traces、usage summary、performance summary、connector status 和 SQLite 备份脚本。
这些能力足够支撑基础排障，但 Pilot 环境还缺少两个边界：

- 出问题时如何导出一份脱敏诊断包给工程师分析。
- 诊断类数据是否清理、何时清理、由谁触发。

当前阶段不应该默认自动删除数据，也不应该把 retention 设计成完整数据生命周期治理。本 change 只定义诊断数据导出和手动清理边界：默认不设置保留时长，默认不自动清理；只有 operator 显式运行 dry-run / apply 时才清理诊断数据。

## What Changes

- 新增 `diagnostics.*` 配置 namespace。
- retention 配置默认 disabled，默认不设置任何保留天数。
- 定义 diagnostics export 本地诊断包：
  - `manifest.json`
  - structured logs
  - trace events 或 trace 摘要
  - usage / performance summary
  - connector status
  - environment summary
  - config key summary
- 导出内容必须二次脱敏，不包含 memory、KB 文档正文 / chunks、完整用户消息、credential、token、API key 或 SQLite 全库备份。
- 新增手动 CLI：
  - `fleetent-admin diagnostics export ...`
  - `fleetent-admin diagnostics retention dry-run`
  - `fleetent-admin diagnostics retention apply`
- retention dry-run / apply 只处理诊断数据：
  - log files
  - observability traces
  - diagnostics export packages
- retention 不删除业务数据：
  - memory
  - KB documents / chunks / vector index
  - users / agents / schedules
  - connector source state
  - SQLite 主库文件
  - 数据库备份
- 更新 observability、deployment、configuration 和 roadmap 文档。

## Out of Scope

- 不做后台 scheduler 自动清理。
- 不设置默认保留时长。
- 不做完整数据生命周期治理。
- 不删除 memory、KB、users、agents、schedules、connector source state 或 vector index。
- 不自动删除数据库备份；只在文档中说明备份保留由部署方管理。
- 不做 UI、HTTP API、dashboard、Prometheus、OpenTelemetry 或外部 APM 集成。
- 不导出 SQLite 全库备份。
- 不导出原始 credential、token、API key 或完整文档正文。

## Module Boundary Impact

- **Owning package**：`observability` owns diagnostics export / trace cleanup policy；`deployment` owns operator
  documentation；`platform/admin CLI` exposes manual commands。
- **Public API surface**：新增 diagnostics export / retention dataclasses 和 functions，例如
  `export_diagnostics()`、`plan_diagnostics_retention()`、`apply_diagnostics_retention()`。
- **Owned tables**：无新表；retention apply 可删除 observability-owned `traces` 表中过期记录。
- **Config namespace**：新增 `diagnostics.*`，默认 disabled 且不设置保留天数。
- **Cross-module dependencies**：diagnostics export 只通过 public APIs 读取 observability summaries 和 connector
  status；不得直接读取 memory / knowledge-base 业务内容。
- **Migration / shim plan**：additive CLI 和 additive API；不迁移已有数据。
