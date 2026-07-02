## MODIFIED Requirements

### Requirement: Read service does not own ingest

本服务 SHALL NOT 拥有 **ingest 管线**:切块 / embedding / 向量入库等**内容与向量写**唯一经 kb-worker(队列消费),本服务 SHALL NOT 改变 ingest(worker / 队列 / connector secret)、SHALL NOT 承载 connector sweep 调度(归 kb-worker)。本服务 MAY 承载 KB **元数据 / 生命周期管理**(建库 / 归档 / 改描述 / 切换 extraction / 删文档)与只读管理 / 评估端点——这些经 `knowledge_base` 模块公共函数直接作用于本租户 `tenants/<tenant>/kb/data/`,与 `fleetent kb create` CLI 及平台 `/admin/kb` 的既有直接写同类,不触碰 ingest 管线。服务进程 SHALL NOT `import fleetent.platform.*`。

#### Scenario: 不拥有 ingest 管线,但可管理元数据
- **WHEN** 检视服务实现
- **THEN** 内容 / 向量写(切块 / embedding / 向量入库)不在本服务内发生,仍唯一经 kb-worker;本服务不改 ingest 队列 / worker / connector secret、不承载 sweep
- **AND** 本服务可经 `knowledge_base` 公共函数执行 KB 元数据 / 生命周期管理与只读管理 / 评估
- **AND** 服务进程不 `import fleetent.platform.*`

## ADDED Requirements

### Requirement: KB 管理端点

kb-serve SHALL 暴露本租户 KB 的管理端点,全复用 `knowledge_base` 模块公共函数、单租户(绑 `config.tenant_id`),鉴权与 `/search` 一致(Bearer service key + ingress principal,principal.tenant_id 须等于绑定租户,跨租户拒绝):

- `POST /kb`(建库)、`GET /kb`(列 KB)、`PATCH /kb/{kb_id}`(改描述 / 切换 extraction)、`DELETE /kb/{kb_id}`(归档)。
- `GET /kb/{kb_id}/documents`(列文档)、`GET /kb/{kb_id}/documents/{document_id}/chunks`(预览 chunk)、`DELETE /kb/{kb_id}/documents/{document_id}`(删文档)。

绑定(KB↔agent)SHALL NOT 由 kb-serve 承载(依赖 management.db 与 agent 身份,归平台)。per-KB observation 指标 SHALL NOT 由 kb-serve 承载(依赖绑定 agent 集与跨 agent 检索 trace,归平台)。

#### Scenario: 建库并管理文档(无 platform)
- **WHEN** 以合法 Bearer + principal 请求 `POST /kb` 建库,再 `GET /kb`、`GET /kb/{kb_id}/documents`
- **THEN** KB 在本租户 `kb.db` 创建,列表 / 文档端点返回本租户对应数据
- **AND** 全程不依赖 platform 或 management.db、服务不 import platform

#### Scenario: 删文档
- **WHEN** `DELETE /kb/{kb_id}/documents/{document_id}`
- **THEN** 经 `knowledge_base` 公共删除函数移除该文档及其 chunk(元数据 / 生命周期写,不经 ingest 管线)

#### Scenario: 跨租户拒绝
- **WHEN** principal.tenant_id ≠ 服务绑定租户
- **THEN** 管理端点返回 403(与 /search、/status 一致)

### Requirement: 离线评估端点

kb-serve SHALL 暴露 `POST /evaluations`,经 `knowledge_base` 检索评估公共 API 对本租户 KB 运行离线检索评估并返回结果,单租户、鉴权与 /search 一致。评估 SHALL NOT 依赖 platform 或 agent 绑定(纯 KB 侧检索质量度量)。

#### Scenario: 运行离线评估
- **WHEN** 以合法 Bearer + principal 请求 `POST /evaluations`(含评估用例)
- **THEN** 服务经 `knowledge_base` 评估 API 运行并返回评分结果,不依赖 platform
