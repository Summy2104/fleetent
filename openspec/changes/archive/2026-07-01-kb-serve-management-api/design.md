## Context

kb-serve 现为只读边（search/status/health）；KB 管理只在平台 in-process。决策：kb-serve 补全管理端点，成为完整单租户 KB 数据面 API（"一个核两条边"的第一步）。管理函数已全在 `knowledge_base.management.runtime`（create/update/set_extraction/archive/list/list_documents/preview_chunks）+ `ingest.runtime.delete_document` + `retrieval.evaluation`，kb-serve 直接复用，几乎不写新逻辑。

## Goals / Non-Goals

**Goals**
- kb-serve 暴露 KB 生命周期 + 文档 + 评估端点，单租户、复用 KB 核。
- 让 KB 成为自包含服务（无 platform 也能经 API 建库/管文档/评估）。

**Non-Goals**
- 不加绑定端点（agent_kbs 依赖 management.db/agent 身份，留平台）。
- 不加 observation（需 bound_agent_ids + 跨 agent trace，kb-serve 拿不到，留平台）。
- 不改平台 `/admin/kb/*` 行为（Change B 才做平台瘦身/契约对齐）。
- 不改 ingest 管线（内容/向量写仍唯一经 kb-worker）。

## Decisions

**D1：读端点直接加,写端点需 MODIFY 只读定位——但单写者纪律不破。**
`kb-read-service` 现有 "Read service does not own ingest / 纯读服务" 要求写死 kb-serve 只读。本 change MODIFY 它：澄清"只读"的真实边界是 **ingest 管线（内容/向量写）唯一归 kb-worker**;KB **元数据/生命周期写**（建库/归档/改描述/删文档）是直接写,kb-serve 可承载——这与 `kb create` CLI、平台 `/admin/kb` 现状**同类**（它们本就直接写 kb.db 元数据）。故非新破坏,是把既有现实写清。仍 SHALL NOT import platform、SHALL NOT 承载 sweep。

**D2：全复用 `knowledge_base` 核函数,serve.py 只加 HTTP 壳。**
每个端点 = 解析请求 → 调对应 management.runtime / ingest.runtime / evaluation 函数（database=注入的本租户 kb_db）→ 包装响应。不在 serve.py 写业务逻辑。响应形状对齐平台 `/admin/kb/*` 现有返回（便于 Change B 平台退成客户端时契约一致）。

**D3：鉴权沿用现有 `_require_authorized_principal`（Bearer service-key + ingress principal,principal.tenant_id 须等于绑定租户）。** 写端点（含 DELETE KB）与读同门:service-key 是 standalone 单租户信任模型的全权凭证,够用。更细的 RBAC（viewer/admin）是平台消费时平台层的事,不在 kb-serve。

**D4：路由形状。** KB 资源走 `/kb`、`/kb/{kb_id}`、`/kb/{kb_id}/documents[/{document_id}[/chunks]]`;评估走 `/evaluations`。与现有 `/search`（body 带 kb_ids）、`/status` 并列,无冲突。

## Risks / Trade-offs

- **并发写 kb.db（kb-serve 元数据写 vs kb-worker 内容写）** → SQLite WAL 单写者锁串行化,元数据写快而稀,安全;且平台/CLI 早已直接写 kb.db 元数据,非新增风险。
- **kb-serve 与平台两条边暂时并存、可能行为微差** → 本 change 令 kb-serve 复用同一核 + 对齐响应形状;彻底消除并存靠 Change B（平台退客户端 or 同核 BFF）。
- **eval 可能写 eval 结果** → 若 evaluation 持久化结果,属 KB 侧写,已在 D1 覆盖;apply 确认 eval 无 platform 依赖（grep 已初步确认 `retrieval.evaluation` 不 import platform）。

## Migration Plan

纯增量,无迁移。无 platform 部署下 kb-serve 即可建库/管文档/评估。回滚 = revert。

## Open Questions

无（Change B 的平台瘦身/跨租户取向是后续决策,不在本 change）。
