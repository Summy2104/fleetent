# Tasks: kb-serve-management-api

> kb-serve 补全 KB 数据面管理端点，全复用 `knowledge_base` 模块函数（serve.py 只加 HTTP 壳）。纯增量，不改平台/worker/绑定/observation。
> 单写者纪律不破：ingest 内容/向量写仍唯一经 kb-worker；本 change 只加元数据/生命周期直接写。
> TDD Hard Gate：测试在实现前，最窄命令红→绿。鉴权全走现有 `_require_authorized_principal`（Bearer service-key + principal，跨租户 403）。

## 1. 读端点（与只读定位不冲突）

- [ ] 1.1 [test-red] `tests/integration/test_kb_serve_management.py`：起 kb-serve（stub embedding），断言 `GET /kb` 列本租户 KB、`GET /kb/{id}/documents`、`GET /kb/{id}/documents/{doc}/chunks` 返回正确数据 + 鉴权（无 Bearer/跨租户 403）。跑 `uv run pytest tests/integration/test_kb_serve_management.py -x -q` → **见红**（端点不存在 404）。
- [ ] 1.2 [impl] `knowledge_base/serve.py` 加 `GET /kb`（`list_knowledge_bases`）、`GET /kb/{kb_id}/documents`（`list_documents`）、`GET /kb/{kb_id}/documents/{document_id}/chunks`（`preview_document_chunks`），均经注入的本租户 kb_db、复用 `_require_authorized_principal`。响应形状对齐平台 `/admin/kb/*` 现有返回。跑 → **见绿**。

## 2. 写端点（元数据/生命周期，直接写）

- [ ] 2.1 [test-red] 扩测试：`POST /kb` 建库（幂等）、`PATCH /kb/{id}`（改描述 + 切 extraction）、`DELETE /kb/{id}`（归档）、`DELETE /kb/{id}/documents/{doc}`（删文档+chunk）；含鉴权与跨租户 403。跑 → **见红**。
- [ ] 2.2 [impl] serve.py 加上述写端点，分别复用 `create_knowledge_base` / `update_knowledge_base_description`+`set_extraction_enabled` / `archive_knowledge_base` / `ingest.runtime.delete_document`。跑 → **见绿**。

## 3. 评估端点

- [ ] 3.1 [test-red] 测试 `POST /evaluations`（用 deterministic fixture，不接真 LLM）返回评分结果 + 鉴权。跑 → **见红**。
- [ ] 3.2 [impl] serve.py 加 `POST /evaluations`，复用 `knowledge_base.retrieval.evaluation` 公共 API；确认 evaluation 无 platform 依赖（grep 已初步确认，impl 时再核）。跑 → **见绿**。

## 4. 收尾门禁（全绿才算完）

- [ ] 4.1 边界护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` + 确认 `serve.py` 无新增 `import fleetent.platform.*`（kb-serve 铁律）；确认**未**添加绑定/observation 端点（本 change 边界）。
- [ ] 4.2 `openspec validate kb-serve-management-api --strict`
- [ ] 4.3 `uv run mypy src`
- [ ] 4.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"（含新增 test_kb_serve_management.py；平台 `/admin/kb/*` 现有测试**应仍全绿**——本 change 不改平台）。
- [ ] 4.5 手验：起 kb-serve → `curl -X POST .../kb -H "Authorization: Bearer <key>" -H 'X-Fleetent-Principal: {"user_id":"u","tenant_id":"default"}' -d '{"kb_id":"t1"}'` 建库 → `GET /kb` 见到 → `POST /kb/t1/... ` 系列可用。
- [ ] 4.6 tasks.md 全 `[x]`；功能分支 `openspec archive kb-serve-management-api`（同步 kb-read-service spec）；**不要扫改 openspec/changes/archive/ 历史产物**；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
