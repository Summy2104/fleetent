## REMOVED Requirements

### Requirement: Per-connector opt-in 周期调度

**Reason**: 平台托管 KB ingest 退役(scope A 全退)——per-connector 周期调度由 standalone KB 服务自有 sweep 取代。
**Migration**: 在 standalone KB 服务的 `kb-service.yaml` 为每个 connector 配 `sync_interval_seconds`,由 KB 服务自有调度器(`standalone_sweep`,见 `kb-standalone-ingest`)按期入本地队列。

### Requirement: 调度经现成队列与 worker

**Reason**: 平台 sweep 入 management.db 队列、由平台 kb-worker drain 的链路退役。
**Migration**: standalone KB 服务自有本地队列 + worker;调度入本地队列(见 `kb-standalone-ingest` 的 "KB-local ingest queue, worker and sweep")。

### Requirement: 轻量去重与重试恢复

**Reason**: 随平台 sweep 一并退役。
**Migration**: 去重/重试语义在 standalone sweep + 本地队列中复用(claim/done/retry 逻辑不变,仅队列后端本地化)。

### Requirement: 多行 sync 历史

**Reason**: 随平台连接器调度退役。
**Migration**: connector 最近状态 / sync 历史由 KB 服务侧记录(per-tenant kb.db 的 `knowledge_connector_status` / `knowledge_connector_sync_history`,本就在 KB 侧)。
