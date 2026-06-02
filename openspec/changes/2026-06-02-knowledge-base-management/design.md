# Design — Knowledge Base Management (Admin 管理面)

本 change 只设计**叠加在 knowledge-base 引擎之上的 Admin 管理面**。引擎语义（解析 / 分块 / vector·keyword·hybrid 检索 / 租户隔离召回 / `delete(document_id)` 级联 / retrieval evaluation）交叉引用 [knowledge-base](../../specs/knowledge-base/spec.md)，向量底座归 vector-store 域，召回注入归 long-term-ctx 域。

## 模块边界

- 新模块 `kb_admin_api.py`：FastAPI `APIRouter(prefix="/admin")`，路由组 `/admin/kb/*`（含 `/admin/agents/{agent_id}/kbs` 反查）。仿 `user_admin_api.py`：登录会话解析（`Authorization: Session <token>` → `auth.validate_session`）→ `auth.has_role` / `require_role` 守卫（写要求 `admin`/`built_in_admin`，读放行 `viewer`）→ 编排引擎调用 → `audit_log.write_audit`。该路由**不 import agent_loop**，可用 TestClient 隔离测试。
- 新模块 `agent_kbs_store.py`：KB↔Agent 绑定表 `agent_kbs` 的读写边界（named params、可 monkeypatch DB 路径、走 Alembic、禁 ORM）。
- **管理面只编排、不重定义检索**：所有解析 / 分块 / 检索 / 删除 / 评估调用都委托给 `knowledge_base` 引擎；管理面不实现任何 chunking / scoring / fusion / embedding 逻辑，也不新接云 embedding 服务。

## 多租户口径

- KB 按 `tenant_id + kb_id` 隔离。私有化单企业部署 `tenant_id` 默认 `default`（对齐引擎 `default_tenant_id="default"`），`default_kb_id="global"`。
- 本管理面所有列表 / 创建 / 导入 / 检索 / 绑定 / 评估均在**当前租户**下进行；请求租户由部署上下文确定（单企业即 `default`）。跨租户可见性由部署方策略决定，本 change 不放开跨租户写。
- `kb_id` 唯一性是 (`tenant_id`, `kb_id`) 复合唯一；重名创建在管理面前置校验后拒绝（场景 104），不落库。

## KB 软删除（归档）+ 绑定保护

- 删除走**软删除（归档）**：归档后该 KB 不再参与召回、从可绑定列表隐去，但 `knowledge_documents` / `knowledge_chunks` / 向量与历史**全部保留**。
- 归档标志落点：优先复用引擎 `knowledge_bases` 表的归档列（如 `archived` / `archived_at`）。若引擎尚无该列，作为 knowledge-base 域 follow-up 补列；管理面**不在自己这边重定义 KB 主表**（避免扩散 SQLite 细节、避免两份 KB 真相）。前置决策见 tasks 0。
- **绑定保护**：归档 / 删除前查 `agent_kbs`——若该 KB 仍被任一 Agent 绑定，则阻止并列出占用 Agent，要求先解绑（场景 106），请求不落库。
- 解档（恢复）允许，恢复后重新参与召回与绑定。

## 文档导入（多入口，编排引擎）

- **粘贴 / 上传**：UI 接收 text / Markdown / 轻量 HTML 内容，调引擎 `ingest_text(filename, content, tenant_id, kb_id, source, source_url)`（必要时先经 `parse_text`/`parse_markdown`/`parse_html` → parsed ingest）；导入即触发 deterministic chunking 与 vector + FTS 索引（引擎职责）。UI 回显每文档解析 / 分块 / 入库结果（分块数、入库状态）。空内容由引擎 fail fast，管理面透传错误。
- **local directory 数据源**：admin 在 UI 配置 allowlisted root，手动触发 `sync_local_directory`；UI 展示 sync summary（scanned / ingested / skipped / failed）。路径越界由引擎 fail fast。目录全量重同步是高危动作，要求二次确认。
- 导入不重启服务即生效（引擎 ingest 同步写库 + 索引）。

## 文档列表与生命周期

- 单 KB 内列出文档的 filename / source / source_url / 分块数 / 创建时间（读引擎文档表，管理面只聚合展示）。
- 分块预览：展示某文档的 chunk content + section context（读引擎 chunk 数据）。
- 单文档删除：调引擎 `delete(document_id)`，级联清理该文档的 chunks + 向量 entries + FTS（引擎职责，幂等）；删除后续检索不再召回该文档（场景 107）。删除写审计，且为高危动作要求二次确认。

## 检索测试台与「聊天试运行」互补

- 检索测试台 `/admin/kb/search`：query + 多选 kb_ids + mode（vector / keyword / hybrid）+ top-k，编排 `knowledge_base.search(query, tenant_id, kb_ids, mode, limit)`，返回不超过 top-k 条召回分块，每条含 score / 所属文档 / position / section context，按引擎稳定排序（score DESC, position ASC, chunk id ASC）。
- **互补定位**：检索测试台只测**召回**（"这个问题能不能召回到对的内容"），是引擎检索的直读；chat-management 的「聊天试运行」测**端到端**（召回 + 模型回答）。两者职责不重叠，本 change 只做前者。
- viewer 可只读使用检索测试台并查看结果（场景 108 中 viewer 仍可浏览检索测试结果）。

## 召回质量评估入口（只读分析）

- `/admin/kb/evaluations`：手动触发引擎的 deterministic retrieval evaluation runner，展示评估批次的命中 / 排序指标。
- **只读**：评估不改索引、不改文档；评估默认 deterministic embedding + isolated storage（引擎语义），管理面**不接真实 embedding / LLM 服务**（遵守 evaluation 域约束）。

## 按 KB 观测（聚合视图）

- KB 详情页展示召回命中次数 / 趋势、被哪些会话引用、长期零召回文档高亮，可下钻到引用该 KB 的会话 trace。
- **数据源为 observability 域**，本页只做按 kb 的聚合视图与下钻入口；若引擎 / observability 需补按 kb 聚合查询，作为 follow-up。

## KB↔Agent 绑定

- `agent_kbs` 表：(`tenant_id`, `kb_id`, `agent_id`) 绑定关系（+ `created_at` / `created_by`）。
- 双向入口：KB 详情页查看 / 调整绑定它的 Agent；Agent 详情页勾选可用 KB（`/admin/agents/{agent_id}/kbs`）。
- 绑定关系供 long-term-ctx 召回注入时按 Agent 限定 kb 范围（注入 / token 预算语义归 long-term-ctx，本 change 只维护绑定真相），供 KB 归档 / 删除的绑定保护复用。
- 仅 admin 可改绑定；viewer 只读。

## 权限与审计

- 权限矩阵（对齐 platform.md）：浏览 KB / 文档 / 检索测试 → admin + viewer；创建 / 编辑 / 归档 KB、导入 / 删除文档、触发同步、按 Agent 绑定 → 仅 admin；运行召回评估 → admin + viewer 只读看结果。
- 所有写操作落 `audit_log.write_audit`（谁 / 何时 / 对哪个 KB·文档 / 做了什么），`action ∈ {kb_create, kb_edit, kb_archive, kb_unarchive, doc_import, doc_sync, doc_delete, kb_bind_agent, kb_unbind_agent, kb_eval_run}`。
- 高危动作（删除 KB / 删除文档 / 目录全量重同步）要求二次确认（沿用 user-management 的 2FA / 二次确认机制）后才执行并落审计。

## 测试隔离（遵循 CLAUDE.md）

- `agent_kbs_store` 复用统一 DB 边界 + 可 monkeypatch DB 路径，测试 monkeypatch 到 `tmp_path`；SQL 用 named params（`:kb_id` 等），不新增 `?` 占位符，不复制 `_init_db()` 建表（schema 归 Alembic）。
- 引擎调用全 mock / 注入：`ingest_text` / `search` / `delete` / `sync_local_directory` / evaluation runner 在管理面单测中用 `unittest.mock` 打桩，断言「编排参数正确 + 透传结果」，不跑真实分块 / 检索。
- 向量与 embedding：管理面单测**不接真实 embedding / 向量服务**；evaluation 入口测试遵守 evaluation 域约束（默认 deterministic / skip 真实 embedding）。
- 路由守卫：FastAPI TestClient 验证 无 session 401、viewer 写 403、admin 放行、高危二次确认；该 router 不 import agent_loop，可在沙箱隔离运行。
- 审计断言：每个写操作后断言 `audit_log` 落一条且字段（actor / action / target / detail）正确。
- 测试分层：路由 + DB + Alembic 走 `tests/integration/`；纯 store / 编排逻辑单测放 `tests/unit/`；不向 `tests/` 根目录新增 `test_*.py`。
