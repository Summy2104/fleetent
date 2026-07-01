## Why

kb-serve 现在只是**只读边**（`/healthz`/`/status`/`/search`）；所有 KB 管理（建/列/改/删 KB、文档、评估）只在**平台 `/admin/kb/*`** 且平台**进程内**直读写 KB 库。这让 KB 不是"自包含服务"——无 platform 环境下无法经 API 建库/管文档/评估，"内测/外部只认一个 KB API"不成立。

本 change 把 kb-serve 补成**完整单租户 KB 数据面 API**：agent / 独立部署 / 外部 / 内测都只认 kb-serve。这是"一个操作核（`knowledge_base` 模块）、两条边（kb-serve HTTP + 平台 in-process）、谁都不重实现"目标的第一步（① kb-serve 补端点；② 平台瘦身另议）。

**边界**（本 change 严格遵守）：
- 只加 KB **数据面**端点（KB 库自有的 CRUD/文档/评估）。**绑定（agent_kbs）不加**——它依赖 management.db + agent 身份，kb-serve 无 agent 概念，留平台。
- **observation 不加**——其聚合需 `bound_agent_ids`（绑定）+ 跨 agent 检索 trace，均在 platform/per-agent 侧，kb-serve 拿不到，留平台。
- **纯增量**：不改平台 `/admin/kb/*` 现有行为（仍 in-process 工作）；平台瘦身/契约对齐是后续 Change B。

## What Changes

kb-serve（`knowledge_base/serve.py`）新增端点，**全复用 `knowledge_base` 模块现成函数**，单租户（绑 `config.tenant_id`），鉴权沿用现有 Bearer service-key + ingress principal：

- **读（与只读定位不冲突，直接加）**：
  - `GET /kb`（列 KB）→ `list_knowledge_bases`
  - `GET /kb/{kb_id}/documents` → `list_documents`
  - `GET /kb/{kb_id}/documents/{document_id}/chunks` → `preview_document_chunks`
  - `POST /evaluations`（离线检索评估）→ `retrieval.evaluation`
- **写（元数据/生命周期，直接写；需 MODIFY kb-serve 只读定位）**：
  - `POST /kb`（建库）→ `create_knowledge_base`
  - `PATCH /kb/{kb_id}`（改描述 / 切换 extraction）→ `update_knowledge_base_description` + `set_extraction_enabled`
  - `DELETE /kb/{kb_id}`（归档）→ `archive_knowledge_base`
  - `DELETE /kb/{kb_id}/documents/{document_id}`（删文档）→ `ingest.runtime.delete_document`

**单写者纪律不破**：ingest 内容/向量写仍**唯一经 kb-worker**（切块/embedding/向量入库）；本 change 只加 KB **元数据/生命周期**直接写（建/归档/改/删文档），与 `kb create` CLI、平台现状同类——不触碰 ingest 管线。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-read-service`：kb-serve 从"纯读服务"扩为"完整单租户 KB 数据面 API"——MODIFY "Read service does not own ingest"（澄清：不碰 ingest 管线/内容写=worker 唯一，但**可承载 KB 元数据/生命周期管理端点与只读管理/评估端点**，仍 SHALL NOT `import fleetent.platform.*`、SHALL NOT 承载 sweep）；ADD KB 管理端点（建/列/改/删 KB、文档列/chunks/删）与离线评估端点两条要求。

## Impact

- **代码**：`knowledge_base/serve.py` 新增 8 端点 + 请求/响应模型（复用 management.runtime / ingest.runtime.delete_document / retrieval.evaluation）。
- **不改**：平台 `/admin/kb/*`（照常 in-process）；kb-worker；绑定；observation（留平台）。
- **spec**：`kb-read-service` delta（MODIFY 只读定位 + ADD 管理/评估端点）。
- **无迁移、无 DB schema 变更、无 `kb-service.yaml` 变更**。
- 兼容：新增端点，无破坏；平台与 kb-serve 暂时并存两条边（都调同一 `knowledge_base` 核），契约对齐/平台瘦身在 Change B。
