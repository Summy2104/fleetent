# kb-read-service — Delta

## MODIFIED Requirements

### Requirement: Read service does not own ingest

本服务 SHALL NOT 拥有 **ingest 消费管线**:切块 / embedding / 向量入库等**内容与向量写**唯一经 kb-worker(队列消费),本服务 SHALL NOT 改变 ingest 消费(worker / connector secret)、SHALL NOT 承载 connector sweep 调度(归 kb-worker)。本服务 MAY 承载 **ingest 投递面**:接收文档上传、暂存文件、向既有 `kb_ingest_jobs` 队列入队(见「文档上传投递端点」),投递 SHALL 止步于入队——消费仍唯一归 kb-worker。本服务 MAY 承载 KB **元数据 / 生命周期管理**(建库 / 归档 / 改描述 / 切换 extraction / 删文档)与只读管理 / 评估端点——这些经 `knowledge_base` 模块公共函数直接作用于本租户 `tenants/<tenant>/kb/data/`,与 `fleetent kb create` CLI 及平台 `/admin/kb` 的既有直接写同类,不触碰 ingest 消费管线。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: 不拥有 ingest 消费管线,但可管理元数据
- **WHEN** 检视服务实现
- **THEN** 内容 / 向量写(切块 / embedding / 向量入库)不在本服务内发生,仍唯一经 kb-worker;本服务不改 ingest worker / connector secret、不承载 sweep
- **AND** 本服务可经 `knowledge_base` 公共函数执行 KB 元数据 / 生命周期管理与只读管理 / 评估
- **AND** 服务进程不 `import fleetent.platform.*`

#### Scenario: 投递面止步于入队
- **WHEN** 上传端点接收一个文档
- **THEN** 本服务只做暂存文件与 `kb_ingest_jobs` 入队;该文档的切块 / embedding / 向量入库在 kb-worker 消费该 job 时才发生

## ADDED Requirements

### Requirement: 文档上传投递端点

kb-serve SHALL 提供 `POST /kb/{kb_id}/documents`(multipart)接收单个文档上传:鉴权与 `/search` 一致(Bearer service key + ingress principal,principal.tenant_id 须等于绑定租户,跨租户拒绝);目标 KB 必须存在(否则 404)。服务 SHALL 将上传字节流式暂存到本租户 uploads 区(`tenants/<tenant>/kb/uploads/<kb_id>/<uuid>-<净化后原名>`,原始文件名剥除路径分隔符后保留为元数据),随后以 `job_type="sync_directory"`、`connector_ref={"path": <暂存路径>}` 入既有 `kb_ingest_jobs` 队列,并返回 job id。上传大小 SHALL 受 `service.max_upload_bytes`(默认 50MB)限制,超限返回 413。暂存文件 SHALL 在 ingest 后保留(作为文档来源,供 reindex 重读)。

#### Scenario: 上传入队并异步入库
- **WHEN** 以合法 Bearer + principal 对已存在的 KB 上传一个文档文件
- **THEN** 文件落 uploads 区、返回 job id;kb-worker 消费后该文档出现在 `GET /kb/{kb_id}/documents`,其内容可被 `/search` 检索

#### Scenario: 大小超限拒绝
- **WHEN** 上传体积超过 `service.max_upload_bytes`
- **THEN** 返回 413,不落暂存文件、不入队

#### Scenario: 文件名净化防路径穿越
- **WHEN** 上传文件名含路径分隔符或 `..`(如 `../../etc/passwd`)
- **THEN** 暂存路径仍严格落在本租户 uploads 区内(uuid 前缀 + 净化名),不发生目录逃逸

#### Scenario: 目标 KB 不存在或跨租户
- **WHEN** kb_id 不存在,或 principal.tenant_id ≠ 服务绑定租户
- **THEN** 分别返回 404 / 403,不落文件、不入队
