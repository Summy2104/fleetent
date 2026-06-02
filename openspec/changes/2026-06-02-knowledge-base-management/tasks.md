> **实施进度（opsx:apply，主体完成）**
> 已按 TDD 实现并通过（沙箱 3.10 + `.pth` UTC shim；不 import agent_loop）：
> - 决策落定：0.3/0.4 KB 主表与归档列归 knowledge-base 引擎域，本 change **只建 `agent_kbs` 绑定表**（迁移 `012`）。引擎调用（list/create/edit/archive/ingest_text/sync/documents/chunks/delete/search/eval/observation）走 sync 接缝（`kb_*`），默认占位 + host 侧按 0.5 确认签名后桥接 async 引擎；测试 mock。
> - 数据层：`agent_kbs_store.py`（db runtime + named params：bind/unbind/list_agents_for_kb/list_kbs_for_agent/is_kb_bound；(tenant_id,kb_id,agent_id) 复合主键 + 租户隔离）。
> - 管理 API：`kb_admin_api.py`（`/admin/kb/*`）——列表（引擎+绑定聚合）、建库（租户内重名 409）、改描述、归档（绑定保护 409 + 二次确认）、文档导入（透传 ingest_text）、目录同步（二次确认）、文档列表/分块预览、单文档删除级联（二次确认）、检索测试台（mode 校验 + 透传 search，viewer 只读可跑）、KB↔Agent 矩阵（双向，反查 `/admin/kb/by-agent/{id}` 避开 /admin/agents 归属）、评估入口（只读）、按 kb 观测。
> - 接线：`server.py` mount `/admin/kb`。权限 `auth.has_role`（admin 写/viewer 只读）+ `audit_log` 审计。
> - 测试：新增 22 个（store 6 + api 16），覆盖场景 103–108；`ruff format/check` 通过。全量 + mypy + 冒烟 + admin.html「知识库」标签需 host 3.12。

## 0. 前置

- [ ] 0.1 确认新模块落点：`kb_admin_api.py`（`/admin/kb/*` + `/admin/agents/{agent_id}/kbs` 反查，仿 `user_admin_api.py`，复用登录会话 + `auth.has_role`/`require_role` + `audit_log`，**不 import agent_loop**）
- [ ] 0.2 确认 KB↔Agent 绑定表 `agent_kbs` 的字段与约束：(`tenant_id`, `kb_id`, `agent_id`) 复合唯一 + `created_at` / `created_by`；走 Alembic、named params（`:kb_id` 等）、DB 路径可 monkeypatch、禁 ORM
- [ ] 0.3 确认 KB 归档标志落点：优先复用引擎 `knowledge_bases` 表归档列（`archived` / `archived_at`）；若引擎尚无该列，作为 knowledge-base 域 follow-up 补列——管理面**不重定义 KB 主表**（前置决策，影响是否需要新 Alembic migration 还是仅依赖引擎 migration）
- [ ] 0.4 确认本 change 需要的 Alembic migration 范围：仅 `agent_kbs`（外加可能的引擎归档列 follow-up）；KB / document / chunk 主表归 knowledge-base 域，不在此重建
- [ ] 0.5 确认引擎编排契约：`ingest_text` / `parse_*` / `sync_local_directory` / `search(query, tenant_id, kb_ids, mode, limit)` / `delete(document_id)` / evaluation runner 的入参与返回形态（用于管理面打桩与透传断言）
- [ ] 0.6 确认跨域 follow-up 边界：long-term-ctx 读 `agent_kbs` 按 Agent 限定 kb 范围（注入 / token 预算语义归 long-term-ctx）；observability 提供按 kb 聚合的召回 / 引用 / 零召回数据源（本 change 只设计管理面，运行语义交叉引用）

## 1. （依赖引擎，前置确认）KB 归档列

- [ ] 1.1 按 0.3 决策：若需引擎补归档列，登记为 knowledge-base 域 follow-up 并在 proposal Impact 标注；本 change 不实现引擎侧 migration
- [ ] 1.2 确认管理面读取引擎 KB 列表时能获取归档状态（archived flag），用于列表标注与绑定可见性过滤

## 2. agent_kbs_store — KB↔Agent 绑定表

- [ ] 2.1 Write failing tests（`tests/integration`，monkeypatch DB 到 `tmp_path`）: Alembic upgrade 后 `agent_kbs` 表存在，含 (`tenant_id`,`kb_id`,`agent_id`) 复合唯一 + `created_at`/`created_by`；named params 写入读出
- [ ] 2.2 新增 Alembic migration（标明 owner module）+ `agent_kbs_store.py`：`bind(tenant_id, kb_id, agent_id, created_by)` / `unbind(...)` / `list_agents_for_kb(tenant_id, kb_id)` / `list_kbs_for_agent(tenant_id, agent_id)` / `is_kb_bound(tenant_id, kb_id)`
- [ ] 2.3 Write failing tests: 重复绑定幂等不报错；`unbind` 删除后 `is_kb_bound` 转 false；`list_kbs_for_agent` 过滤已归档 KB
- [ ] 2.4 实现上述行为

## 3. kb_admin_api — KB 列表 / 创建 / 编辑 / 归档 + 绑定保护

- [ ] 3.1 Write failing tests（TestClient）: 无 session 401；viewer 可 `GET /admin/kb` 列表；列表含 kb_id/描述/文档数·分块数/最近导入/绑定 Agent（引擎调用打桩）
- [ ] 3.2 实现 `GET /admin/kb` 列表（编排引擎 KB 列表 + `agent_kbs` 绑定聚合 + 归档标注）+ 搜索排序
- [ ] 3.3 Write failing tests: admin `POST /admin/kb` 建 KB；重名（tenant 内）拒且不落库（场景 104）；viewer 创建 403（场景 108）
- [ ] 3.4 实现创建（前置唯一性校验 + 写审计 `kb_create`）
- [ ] 3.5 Write failing tests: `PATCH /admin/kb/{kb_id}` 改描述写审计 `kb_edit`；`DELETE /admin/kb/{kb_id}` 在仍被绑定时阻止并列占用 Agent、不落库（场景 106）；无绑定时归档保留文档写审计 `kb_archive`
- [ ] 3.6 实现编辑 + 归档（绑定保护查 `agent_kbs_store.is_kb_bound`，高危二次确认）

## 4. kb_admin_api — 文档导入（多入口）

- [ ] 4.1 Write failing tests: admin 粘贴/上传 text·md·html → 调引擎 `ingest_text`（断言 tenant_id/kb_id/source 透传）→ 回显分块数/入库结果（场景 103）；viewer 导入 403（场景 108）
- [ ] 4.2 实现粘贴/上传导入端点（编排 `ingest_text`/`parse_*`，引擎 mock，写审计 `doc_import`）
- [ ] 4.3 Write failing tests: 配 local directory + 触发 `sync_local_directory` → 返回 scanned/ingested/skipped/failed summary；全量重同步要求二次确认
- [ ] 4.4 实现 local directory 同步端点（编排 `sync_local_directory`，写审计 `doc_sync`）

## 5. kb_admin_api — 文档列表 / 分块预览 / 单文档删除级联

- [ ] 5.1 Write failing tests: `GET /admin/kb/{kb_id}/documents` 列 filename/source/分块数/创建时间（viewer 可读）；分块预览含 content + section context
- [ ] 5.2 实现文档列表 + 分块预览（读引擎文档/chunk 数据，只聚合展示）
- [ ] 5.3 Write failing tests: `DELETE /admin/kb/{kb_id}/documents/{document_id}` 调引擎 `delete(document_id)` 级联清理、后续不召回、写审计 `doc_delete`、高危二次确认（场景 107）；viewer 删除 403
- [ ] 5.4 实现单文档删除（编排 `delete`，二次确认 + 审计）

## 6. kb-retrieval-playground — 检索测试台

- [ ] 6.1 Write failing tests: `POST /admin/kb/search` query + 多选 kb_ids + mode(hybrid) + top-k=5 → 调引擎 `search` 返回 ≤5 条，每条含 score/所属文档/position/section，稳定排序（场景 105）
- [ ] 6.2 实现检索测试台端点（编排 `knowledge_base.search`，透传 mode 与 kb_ids，引擎 mock）
- [ ] 6.3 Write failing tests: 未知 mode fail fast；viewer 可只读运行并看结果（场景 108）；多选 kb_ids 透传
- [ ] 6.4 实现 mode 校验透传 + viewer 只读放行

## 7. kb-agent-binding — KB↔Agent 矩阵端点

- [ ] 7.1 Write failing tests: admin `POST /admin/kb/{kb_id}/agents`/`DELETE` 绑定/解绑写审计 `kb_bind_agent`/`kb_unbind_agent`；`GET` 两侧（`/admin/kb/{kb_id}/agents`、`/admin/agents/{agent_id}/kbs`）一致；viewer 改 403、读放行
- [ ] 7.2 实现绑定/解绑/双向查询端点（编排 `agent_kbs_store`，写审计）
- [ ] 7.3 Write failing tests: 绑定后该 KB 归档被阻止（与 3.5 联动）；解绑后可归档
- [ ] 7.4 接线绑定保护到归档路径

## 8. kb-eval-entry — 召回质量评估入口（只读）

- [ ] 8.1 Write failing tests: `POST /admin/kb/evaluations` 触发引擎 deterministic evaluation runner（mock），返回命中/排序指标；不改索引/文档；默认不接真实 embedding；viewer 可只读看结果
- [ ] 8.2 实现评估入口端点（编排 evaluation runner，写审计 `kb_eval_run`，只读）

## 9. kb_admin_api — 按 KB 观测聚合视图

- [ ] 9.1 Write failing tests: `GET /admin/kb/{kb_id}/observation` 返回按 kb 聚合的召回命中/趋势/零召回文档/引用会话（observability 数据源打桩）；只读不改索引
- [ ] 9.2 实现按 kb 聚合视图（消费 observability 数据源，仅聚合与下钻入口；缺失字段登记 follow-up）

## 10. server 接线 + 管理控制台 + 收尾

- [ ] 10.1 Write failing tests: `server.py` mount `/admin/kb` router；TestClient 走通登录会话 → KB 列表/检索测试
- [ ] 10.2 改 `server.py` mount kb router；`admin.html` 追加「知识库」标签（vanilla JS 调 `/admin/kb/*`）
- [ ] 10.3 全量 `uv run pytest -x -q` 绿
- [ ] 10.4 `uv run ruff format src tests && uv run ruff check src tests && uv run mypy src` 通过
- [ ] 10.5 手动冒烟：建 KB → 粘贴导入 + 配目录同步 → 文档列表/分块预览 → 检索测试台 hybrid top-k → 绑定 Agent → 绑定时归档受阻 → 解绑后归档 → 删文档级联 → 评估入口看指标 → viewer 全程只读 + 写 403 + 审计检索
