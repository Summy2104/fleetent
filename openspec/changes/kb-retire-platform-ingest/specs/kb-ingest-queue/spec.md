## MODIFIED Requirements

### Requirement: 持久 ingest job 队列

系统 SHALL 提供持久的 DB 背 ingest job 队列,归 **standalone KB 服务本地**(KB 主机本地 SQLite,**非** management.db / 非平台)。每条 job SHALL 含 `id`、`tenant_id`、`kb_id`、`connector_ref`(非密 connector 配置引用/内容)、`cred_ref`(本地凭据引用 `env:`/`file://`,**非明文**)、`status`(pending/claimed/done/failed)、`attempts`、创建/认领/完成时间戳。平台托管的 management.db 队列(`kb_ingest_jobs` in management.db)**已退役**。

#### Scenario: standalone 入队产生 pending job

- **WHEN** standalone KB 服务的 ingest 触发(自有 sweep 的 connector sync / 自动 extraction)发生
- **THEN** 系统在 KB 本地队列插入一条 `status=pending` 记录,携带 `connector_ref` 与本地 `cred_ref`
- **AND** 不读写 management.db

#### Scenario: 明文凭据不入队

- **WHEN** 入队时读取 connector 配置
- **THEN** job 只写入凭据的**本地引用**(`cred_ref`,`env:`/`file://`),不写入明文凭据
