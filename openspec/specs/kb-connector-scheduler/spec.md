# kb-connector-scheduler Specification

## Purpose
TBD - created by archiving change kb-connector-scheduler. Update Purpose after archive.

## Requirements

### Requirement: KB connector 周期调度归 standalone 服务所有
平台托管 KB ingest 退役后，KB connector 的周期调度 SHALL 只由 standalone KB 服务负责。connector 的 `sync_interval_seconds` 配置 SHALL 存放在 `kb-service.yaml`，由 KB 服务自有 `standalone_sweep` 按期入本地队列；platform 控制面 SHALL NOT 再承担该调度责任。

#### Scenario: standalone 未配置时不调度
- **WHEN** standalone KB 服务中的某 connector 未设置 `sync_interval_seconds`
- **THEN** KB 服务自有调度器不会为它入队任何 sync job

#### Scenario: standalone opt-in 后按间隔调度
- **WHEN** 一个 enabled connector 设了 `sync_interval_seconds=N`，且距上次调度已 ≥ N 秒
- **THEN** 下一次 standalone sweep 为它入队一个本地 `connector_sync` job

#### Scenario: 禁用的 connector 不调度
- **WHEN** 一个 connector `enabled=0` 但设了 `sync_interval_seconds`
- **THEN** standalone sweep 不为它入队
