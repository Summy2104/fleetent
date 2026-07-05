# kb-ingest-upload-path — Design

## Context

retire-platform-ingest 之后，ingest 的一切（队列、worker、connector 配置）收进 KB 服务自包含；kb-read-service spec 用 "Read service does not own ingest" 把 serve 封为纯读 + 元数据管理。现状：入库唯二通路 = KB 宿主机 CLI（`fleetent kb ingest`）与 connectors.yaml 定时同步，平台管理员无从上传。

既有可复用件：serve 的 `_require_authorized_principal`（Bearer + principal 头 + 租户校验）；`fleetent.kb_ingest_jobs.enqueue_job`（`sync_directory` 类型对单文件/目录通吃，`connector_ref={"path": ...}`，worker 消费）；platform 侧 `KBServeClient`（url + service key，per-tenant principal 头）与 `/admin/kb` 代理模式 + `_require_admin`/审计惯例。

## Goals / Non-Goals

**Goals:**

- 平台管理员经 `/admin/kb/{kb_id}/documents` 上传单个文档，内容异步进入该 KB（worker 消费，状态可经既有 `/status`、documents 列表观测）。
- 保住拓扑不变量：KB 中心仍是唯一访问点；内容/向量写仍唯一经 kb-worker；serve 不 import platform。

**Non-Goals:**

- 不做批量/目录上传（单文件 multipart；批量 = 多次调用）。
- 不做 connector 管理回平台。
- 不做 SPA 上传框（属 kb-admin-ui-completion）。
- 不做暂存文件生命周期管理（删文档联动清理 deferred，见 Risks）。
- 不做上传内容的同步 ingest（不等结果，返回 job id 即止）。

## Decisions

**D1 — 上传口开在 kb serve，platform 只做薄代理。**
替代方案 a）platform 直接写队列：队列 db 在 KB 宿主机，platform 可能异机，且违反"platform 零 KB ingest"收敛方向，拒绝。b）新开独立上传服务：多一个进程与端口，无必要。serve 已持有租户数据目录与队列 url（同 `service_config`），是唯一天然落点。

**D2 — 端点语义 = 暂存 + 入队，复用 `sync_directory` job 类型。**
上传字节落 `tenants/<tenant>/kb/uploads/<kb_id>/<uuid>-<sanitized-name>`，随后 `enqueue_job(job_type="sync_directory", connector_ref={"path": <staged file>})`——与 `fleetent kb ingest` 单文件路径完全同构，worker 零改动。替代方案——serve 内直接切块/嵌入：违反"内容/向量写唯一经 worker"铁律，拒绝。

**D3 — spec 修订用 MODIFIED 显式解封，不新开并列 requirement。**
"Read service does not own ingest" 是刻意封条；在其上叠一条 ADDED "但可以上传"会造成两条 requirement 互相矛盾。MODIFIED 全文改写：serve MAY 承载**投递面**（接收上传、暂存、入队），SHALL NOT 承载消费面（切块/embedding/向量写/sweep）。

**D4 — 暂存文件保留为文档来源，不即焚。**
`sync_directory` 语义 = 磁盘路径是内容来源；reindex 场景可能重读。删文档时联动清理暂存文件列 deferred（uploads 区按 kb_id 分目录，未来可批量清）。替代方案——ingest 完成即删：reindex 后该文档凭空消失，语义破坏，拒绝。

**D5 — 上传约束在 serve 端强制：`service.max_upload_bytes`（默认 50MB）超限 413；暂存文件名 = uuid 前缀 + 净化原名（剥路径分隔符），原始文件名进文档元数据。**
路径穿越防御在 serve 端做（不信任代理层）；platform 代理不重复限制（透传 413）。

**D6 — 审计在 platform 代理层记 `doc_upload`（actor = admin user），与 `doc_delete` 等既有审计对称。**
serve 端无管理库不记平台审计；serve 侧可观测性靠既有 job 状态（`/status`）。

## Risks / Trade-offs

- **[uploads 区无限增长]** 暂存文件只进不出。→ Mitigation：按 `<kb_id>/` 分目录便于人工/未来自动清理；deferred 项显式记录（删文档联动清理 + 归档 KB 清理整目录）。
- **[大文件/慢连接占住 serve worker 线程]** multipart 读取期间占用连接。→ Mitigation：`max_upload_bytes` 上限 + FastAPI 流式读到暂存文件（不整体载入内存）。
- **[上传成功但 ingest 失败的观测断层]** 返回 job id 后失败只在 job 状态里。→ Mitigation：响应体带 job id，文档列表 + `/status` 已能反映；admin API 侧不做轮询封装（UI 层 change 处理展示）。
- **[与 kb-binding-provider-materialize 的文件交叠]** 双方都改 `kb_serve_client.py`。→ Mitigation：apply 顺序约束——materialize change 先落 main；本 change apply 前 pull。

## Migration Plan

无 DB 迁移、无配置强制项（`max_upload_bytes` 有默认值）。部署顺序：KB 服务先升级（新端点），platform 后升级（代理路由）——反序时代理调不存在的端点得 404，无数据风险。回滚各自独立回退。

## Open Questions

- 暂存区清理策略（删文档/归档 KB 联动 vs 定期 sweep）——deferred，等真实容量压力再立项。
- 是否需要文本粘贴式入库（非文件）——本次不做，需求出现时是同端点加 content-type 分支的小活。
