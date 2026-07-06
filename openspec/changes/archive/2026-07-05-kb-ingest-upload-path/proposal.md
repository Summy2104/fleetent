# kb-ingest-upload-path

## Why

平台管理员目前没有任何把文档送进 KB 的通路：`/admin/kb/*` 只能管理已入库内容（列/删/搜/评估/绑定），入库只能登录 KB 服务宿主跑 `fleetent kb ingest` 或手编 connectors.yaml。"KB 在 Platform 侧可简单管理"因此缺了最基本的一环——内容进不去。retire-platform-ingest 当年把 ingest 收进 KB 自包含是正确方向，本 change 不回退它：新开的上传口在 **kb serve 侧**（暂存 + 入队），worker 消费管线零改动，platform 只做薄代理。

## What Changes

- **kb serve 新增受保护上传端点** `POST /kb/{kb_id}/documents`（multipart）：鉴权与 `/search` 一致（Bearer service key + ingress principal + 租户校验）；将上传文件暂存到本租户 KB 数据目录下的 uploads 区，再经 `kb_ingest_jobs.enqueue_job(job_type="sync_directory", connector_ref={"path": <staged>}) ` 入既有队列；响应返回 job id。切块/embedding/向量写仍唯一经 kb-worker——serve 只投递，不消费。
- **kb-read-service spec 的 "Read service does not own ingest" 修订**：从"不承载任何 ingest 面"放宽为"可承载**投递面**（暂存 + 入队），内容/向量写仍唯一经 worker"。这是对既有封条的显式解封，非绕过。
- **platform admin API 新增代理路由** `POST /admin/kb/{kb_id}/documents`（multipart 透传，`KBServeClient` 加 upload 方法），admin-only + 审计（`doc_upload`）。
- 上传约束：大小上限（`service.max_upload_bytes`，默认 50MB）、文件名净化（暂存名用 uuid，原名留元数据）。
- **不做**：connector 管理仍留 KB 侧 connectors.yaml；SPA 上传框属 change kb-admin-ui-completion；上传文件的生命周期清理（删文档时同步清暂存）记 deferred。

## Capabilities

### New Capabilities

（无）

### Modified Capabilities

- `kb-read-service`：修订 "Read service does not own ingest"（放行投递面）；"KB 管理端点"清单增加上传端点。
- `kb-admin-api`：新增文档上传代理 requirement（admin-only、审计、透传 kb serve）。

## Impact

- **Owning package**：`fleetent.knowledge_base`（serve 上传端点 + 暂存）+ `fleetent.platform.knowledge_base_management`（代理路由 + client 方法）。
- **Public API surface**：kb serve 新增 `POST /kb/{kb_id}/documents`；platform 新增 `POST /admin/kb/{kb_id}/documents`。
- **Owned tables**：无新表（复用 `kb_ingest_jobs` 队列）。
- **Config namespace**：`kb-service.yaml` 的 `service` 段新增可选 `max_upload_bytes`（默认 50MB）。
- **Cross-module dependencies**：serve 依赖 `fleetent.kb_ingest_jobs`（既有）；serve 仍 MUST NOT import `fleetent.platform.*`。
- **Migration / shim plan**：无迁移。注意 kb-admin-ui spec 中"SPA 不调 `POST /admin/kb/{id}/documents`（retired）"的断言属 SPA 侧封条，由 change kb-admin-ui-completion 修订，本 change 不碰前端。
- **与并行 change 的文件交叠**：`kb_serve_client.py` 同时被 kb-binding-provider-materialize（提升 `_resolve_auth_ref` helper）触碰——**建议该 change 先合 main 再 apply 本 change**（或 apply 前 rebase）。
