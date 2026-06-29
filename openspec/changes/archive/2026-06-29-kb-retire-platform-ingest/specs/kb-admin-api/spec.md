## REMOVED Requirements

### Requirement: Document import via multiple entry points

**Reason**: 平台托管 KB ingest 退役——文档导入不再经平台 admin 入 management.db 队列。
**Migration**: 文档摄取由 standalone KB 服务承担(connector 自动同步,或 KB 服务侧导入入口);平台不再提供 `POST /{kb_id}/documents` / `/{kb_id}/sync`。

### Requirement: Connector sync 经队列异步执行

**Reason**: 平台连接器管理与同步退役(scope A 全退)。
**Migration**: connector 配置与同步归 standalone KB 服务(`kb-service.yaml` 的 connectors + 自有 sweep + 本地队列);平台不再提供 `/admin/kb/connectors/*`。

### Requirement: Manual KB entity extraction trigger

**Reason**: 显式 entity extraction 触发随平台 ingest 退役;extraction 归 KB 服务。
**Migration**: 自动 extraction 在 standalone ingest 内按 KB `extraction_enabled` 入本地队列触发;显式触发(如需)由 KB 服务侧入口提供,平台不再提供 `/{kb_id}/extract-entities`。
