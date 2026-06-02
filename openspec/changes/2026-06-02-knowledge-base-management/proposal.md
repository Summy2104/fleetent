## Why

knowledge-base 引擎（解析 / 分块 / vector·keyword·hybrid 检索 / 租户隔离召回 / `delete(document_id)` 级联 / deterministic retrieval evaluation）已在 archive 设计并落地，向量底座归 vector-store 域，召回注入归 long-term-ctx 域。但**领域专家无法用代码**：今天要新建一个 KB、喂进企业文档、验证"这个问题能不能召回到对的内容"、把 KB 绑给某个 Agent，全得改代码或写脚本。

对照 `platform.md`«知识库管理（v1.0）»的缺口：

1. **没有 KB 管理面**：无法在后台列出当前租户的 KB（kb_id / 描述 / 文档数·分块数 / 最近导入 / 被哪些 Agent 绑定），更没有 UI 新建 / 编辑 / 归档。
2. **没有文档导入入口**：`ingest_text` / `parse_*` / `sync_local_directory` 只有代码路径，admin 无法在 UI 粘贴 / 上传 text·md·html 或配置 local directory 数据源并手动触发同步。
3. **没有文档生命周期视图**：看不到单 KB 内文档的 filename / source / 分块数，无法预览某文档分块、无法单独删除（级联清理 chunks / 向量）。
4. **检索只能靠想象**：没有检索测试台（query + 多选 KB + 模式 + top-k → 召回分块 / score / position / section），无法在喂数据后即时验证召回质量。
5. **KB↔Agent 绑定不可视**：哪些 KB 对哪个 Agent 可见没有可视化矩阵，long-term-ctx 按 Agent 限定 kb 范围、删除绑定保护都缺一份权威绑定关系。
6. **召回质量评估无入口**：deterministic retrieval evaluation 只能命令行跑，admin 看不到命中 / 排序指标。
7. **无权限分层与审计**：建 / 删 / 导入 / 触发同步等写操作没有 admin/viewer 分层，也没有审计与高危二次确认。

本 change 把这些补齐为一套叠加在引擎之上的**知识库 Admin 管理面**——只编排引擎调用、不重定义检索语义。

## What Changes

**ADDED**

- `kb-admin-api`：`/admin/kb/*` FastAPI 路由（仿 `user_admin_api.py`，登录会话 + `auth.has_role`/`require_role` 守卫 + `audit_log`）。涵盖 KB 列表（kb_id / 描述 / 文档数·分块数 / 最近导入 / 绑定 Agent / 向量命名空间概况，可搜索排序）、创建 / 编辑（租户内 kb_id 唯一，重名拒）、软删除（归档）+ 绑定保护、文档导入多入口（粘贴 / 上传 text·md·html → `ingest_text`；配置 local directory 数据源并手动触发 → `sync_local_directory`）、文档列表与生命周期（分块预览、单文档删除级联 → `delete(document_id)`）、按 KB 观测聚合视图、权限与审计。
- `kb-retrieval-playground`：检索测试台 `/admin/kb/search`。query + 多选 KB + 模式（vector / keyword / hybrid）+ top-k，编排 `knowledge_base.search` 返回召回分块及其 score / 所属文档 / position / section context，稳定排序；viewer 可只读看结果。
- `kb-agent-binding`：KB↔Agent 可视化矩阵 `/admin/kb/{kb_id}/agents`、`/admin/agents/{agent_id}/kbs`，持久化到新 `agent_kbs` 绑定表；供 long-term-ctx 在召回注入时按 Agent 限定 kb 范围（实际注入语义以 long-term-ctx 为准），供 KB 删除绑定保护复用。
- `kb-eval-entry`：手动触发 deterministic retrieval evaluation 的 UI 入口 `/admin/kb/evaluations`，展示评估批次的命中 / 排序指标；只读分析，不改索引、不接真实 embedding。

## Capabilities

### New Capabilities

- `kb-admin-api`
- `kb-retrieval-playground`
- `kb-agent-binding`
- `kb-eval-entry`

## Impact

- **代码**：
  - 新增：`kb_admin_api.py`（`/admin/kb/*` 路由：列表 / CRUD / 导入 / 文档生命周期 / 检索测试 / 绑定 / 评估 / 观测聚合，登录会话守卫 + 审计，**不 import agent_loop**，TestClient 可隔离测）；`agent_kbs_store.py`（KB↔Agent 绑定表读写）。
  - 修改：`server.py`（mount kb router）；`admin.html`（管理控制台追加「知识库」标签，vanilla JS 调 `/admin/kb/*`）。
- **复用 knowledge-base 引擎 API（不重造）**：导入复用 `ingest_text` / `parse_text`·`parse_markdown`·`parse_html` / `sync_local_directory`；检索复用 `search(query, tenant_id, kb_ids, mode, limit)` 三模式；删除复用 `delete(document_id)`（级联 chunks + 向量 + FTS）；评估复用 deterministic retrieval evaluation runner。embedding / 向量调用一律落到引擎，管理面不新接任何云 embedding 服务。
- **数据**：新增 `agent_kbs` 绑定表（走 Alembic）；KB 归档标志（落点见 design：优先复用引擎 `knowledge_bases` 表的 `archived` 列，需引擎补列则作为 follow-up 由 knowledge-base 域加；本 change 不在管理面重定义 KB 主表）。`kb_id` 唯一性约束在租户内 (`tenant_id`,`kb_id`)。
- **跨域 follow-up**：
  - long-term-ctx：召回注入时读取 `agent_kbs` 按 Agent 限定 kb 范围（实际注入 / token 预算语义归 long-term-ctx 域，本 change 只提供并维护绑定关系）。
  - observability：按 KB 聚合的召回命中次数 / 趋势 / 零召回文档 / 引用会话 trace 由 observability 域提供数据源，本页只做按 kb 的聚合视图与下钻入口。
  - knowledge-base：若软删除归档标志、按 KB 观测计数等需要引擎侧补字段或暴露查询，作为引擎域 follow-up。
- **认证依赖**：复用 user-management 的登录会话 + `auth.has_role`/`require_role`（写要求 admin、读放行 viewer）+ `audit_log` + 高危二次确认机制。
- **破坏性**：无。纯叠加管理面与一张绑定表；不改引擎检索 / 删除 / 隔离语义。

## Commit 切分建议

每个 commit 自包含、内部 TDD（测试先红 → 实现 → 绿）：

1. `feat(agent_kbs_store): agent_kbs binding table + read/write + migration`（2.x）
2. `feat(kb_admin_api): KB list / create / edit / archive with binding protection`（3.x）
3. `feat(kb_admin_api): document import (paste·upload / local directory sync)`（4.x）
4. `feat(kb_admin_api): document list / chunk preview / cascade delete`（5.x）
5. `feat(kb_admin_api): retrieval playground (query + multi-KB + mode + top-k)`（6.x）
6. `feat(kb_admin_api): KB↔Agent binding matrix endpoints`（7.x）
7. `feat(kb_admin_api): retrieval evaluation entry (read-only metrics)`（8.x）
8. `feat(kb_admin_api): per-KB observation aggregation view + audit`（9.x）
9. `feat(server): mount /admin/kb router + admin console KB tab`（10.x）
