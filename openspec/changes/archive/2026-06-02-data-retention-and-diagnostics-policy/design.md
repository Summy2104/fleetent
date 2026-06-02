## Context

当前已有数据落点：

- structured logs：`data/logs/YYYY-MM-DD.log` 和 `data/logs/YYYY-MM-DD.error.log`。
- traces：observability-owned SQLite `traces` 表。
- usage / performance summary：从 trace public API 聚合。
- connector status：由 `knowledge-base-connector-operations` 计划新增最近一次状态表。
- database backups：`scripts/upgrade.py` 创建 `data/backups/YYYYMMDD-HHMMSS/fleetent.db`。

这些数据服务于不同目的。Pilot 阶段最需要的是可排障和不误删。

## Configuration

新增配置建议：

```yaml
diagnostics:
  export_dir: data/diagnostics
  retention:
    enabled: false
    logs_days:
    traces_days:
    diagnostic_exports_days:
```

语义：

- `enabled=false`：不允许 `retention apply` 执行删除，只允许 dry-run 展示计划。
- `enabled=true` 且某个字段为空：该数据类型不清理。
- 字段为正整数天数：允许清理超过该天数的数据。
- 未配置 diagnostics namespace 时使用默认值：export_dir 为 `data/diagnostics`，retention disabled。

本 spec 不提供 backups_days。数据库备份是否删除由部署方管理，避免误删恢复点。

## Diagnostics Export

`fleetent-admin diagnostics export` 生成本地压缩包。建议结构：

```text
diagnostics-YYYYMMDD-HHMMSS.zip
  manifest.json
  logs/
    YYYY-MM-DD.log
    YYYY-MM-DD.error.log
  traces/
    events.jsonl
    usage_summary.json
    performance_summary.json
  knowledge_connectors/
    status.json
  environment.json
  config_summary.json
```

导出参数建议：

- `--from`
- `--to`
- `--output-dir`
- `--include-logs / --no-logs`
- `--include-traces / --no-traces`
- `--include-connector-status / --no-connector-status`

默认导出最近一段时间的诊断数据，具体默认时间窗口可在实现阶段保守选择，例如最近 24 小时；但这不是 retention 保留时长。

### Export Includes

- manifest：导出时间、fleetent 版本、时间范围、包含的数据类型、脱敏版本。
- logs：指定时间范围内的 structured log 文件，写入压缩包前再做脱敏。
- traces：指定时间范围内的 trace events 或摘要，写入前脱敏和截断。
- usage / performance：聚合 summary。
- connector status：最近一次 connector status / summary / error。
- environment summary：Python 版本、平台、时区、进程相关非 secret 信息。
- config summary：配置 key、开关和非 secret 值摘要。

### Export Excludes

- memory 内容。
- KB 文档正文、chunks、parser 原文。
- 完整用户消息、完整 prompt、完整 reply。
- API keys、tokens、OAuth credential、Confluence API token。
- SQLite 主库文件。
- SQLite 全库备份。
- connector credential 文件内容。

## Redaction

diagnostics export 必须在写包前二次脱敏，即使 logs / traces 写入时已经做过脱敏。

脱敏规则至少覆盖：

- Bearer token。
- API key。
- password / secret / token / authorization 字段。
- 邮箱。
- 中国大陆手机号。
- credential_ref 指向的文件内容。

对于 trace payload 中可能出现的大文本，export 应做长度限制，并保留 `truncated=true` 标记。

## Retention

retention 分 dry-run 和 apply。

### Dry-run

`fleetent-admin diagnostics retention dry-run` 输出将删除的候选：

- logs 文件数量和路径摘要。
- traces 记录数量。
- diagnostics export 包数量和路径摘要。

dry-run 不修改文件系统和数据库。

### Apply

`fleetent-admin diagnostics retention apply` 仅在 `diagnostics.retention.enabled=true` 时允许删除。

允许删除：

- 超过 `logs_days` 的 `data/logs/*.log` / `*.error.log`。
- 超过 `traces_days` 的 `traces` 表记录。
- 超过 `diagnostic_exports_days` 的 diagnostics export 包。

不允许删除：

- memory。
- KB documents / chunks。
- vector index。
- users / agents / schedules。
- connector source state。
- SQLite 主库。
- SQLite backups。

apply 输出删除摘要；单个文件删除失败应记录失败并继续处理其他候选。

## CLI

建议命令：

```bash
fleetent-admin diagnostics export --from 2026-06-02T00:00:00 --to 2026-06-02T23:59:59
fleetent-admin diagnostics retention dry-run
fleetent-admin diagnostics retention apply
```

如果 `retention.enabled=false`，`apply` 应 fail fast，并提示需要显式开启配置。

## Testing

测试重点：

- 默认配置 retention disabled 且所有天数字段为空。
- export 生成 manifest 和预期文件结构。
- export 不包含 memory / KB 内容 / credential / SQLite DB。
- export 对 logs / traces / config summary 做二次脱敏。
- dry-run 不删除文件和 trace 记录。
- apply 在 disabled 时拒绝执行。
- apply enabled 且字段为空时不删除对应数据类型。
- apply enabled 且设置天数时只删除诊断数据。
- apply 不删除 backups。
- CLI 输出不包含 secret。

## Non-Goals

本 change 不解决：

- 自动清理调度。
- 备份生命周期自动管理。
- 合规级数据删除请求。
- 用户数据导出。
- 全量审计报表。
- 外部 observability 平台集成。
