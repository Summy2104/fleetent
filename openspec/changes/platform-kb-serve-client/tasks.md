# Tasks: platform-kb-serve-client (Change B)

> **gated on Change C 落地**（多租户 kb-serve + 共享 service-key）：开工前 `git pull origin main` 确认 C 已在 main；apply 时对齐 C 落地的 kb-serve 地址/鉴权/多租户路由。
> 平台 KB 数据面退成 kb-serve HTTP 客户端；**绑定 + observation 不动**（in-process，搬不走）。与 Change D 无文件重叠，可并行。
> TDD Hard Gate：测试在实现前，最窄命令红→绿。

## 1. 平台侧 kb-serve 客户端

- [ ] 1.1 [test-red] 测新增 kb-serve 客户端：为目标租户 mint principal + 带共享 key，调 kb-serve 的 search / kb CRUD / documents / eval（可对 kb-serve stub 或 C 落地的多租户 kb-serve）。跑最窄命令 → 见红。
- [ ] 1.2 [impl] 新增 `platform/knowledge_base_management/` 下 kb-serve HTTP 客户端：读平台配置的中心 kb-serve URL + 共享 service key；每调用编码 `X-Fleetent-Principal`(目标租户) + Bearer key；覆盖 Change A 的 kb-serve 端点。平台配置加中心 kb-serve URL + service key 引用项。跑 → 见绿。

## 2. 改写 /admin/kb 数据面 handler 走客户端

- [ ] 2.1 [test-red] 改集成测：`/admin/kb` 列/建/改/归档、documents/chunks/删文档、`/search`、`/evaluations` 经 kb-serve 客户端执行（不再 in-process 直读）；`/search` 透传 rerank/use_planner 并返回对齐 kb-serve 的 KnowledgeChunk。跑 → 见红。
- [ ] 2.2 [impl] 改写 `kb_admin_api.py`：`kb_engine_list/create/edit/archive`、`kb_search`、documents/chunks/删文档、evaluations → 调 kb-serve 客户端。`/admin/kb/search` 请求体 `top_k→limit` + 透传 rerank/use_planner，响应对齐 KnowledgeChunk（`id` 非 `chunk_id`）。跑 → 见绿。
- [ ] 2.3 [impl] 编排型 handler（如建 KB 后绑定）：KB 部分走 kb-serve、绑定部分走 in-process；保证幂等（建 KB 幂等 + 绑定可重试），跨两侧无强事务。

## 3. 绑定 + observation 保持 in-process（回归守护）

- [ ] 3.1 [test] 断言 `/admin/kb/{id}/agents`、`/admin/agents/{name}/kbs`、`/admin/kb/{id}/observation` **仍 in-process**（agent_kbs @ management.db / kb_observation 聚合未改、未走 kb-serve）；平台 session + RBAC 鉴权保持。

## 4. 收尾门禁

- [ ] 4.1 边界护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`（平台调 kb-serve 是 HTTP 客户端，非 import KB 内部）。
- [ ] 4.2 `openspec validate platform-kb-serve-client --strict`
- [ ] 4.3 `uv run mypy src`
- [ ] 4.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"。
- [ ] 4.5 手验：平台配中心 kb-serve URL → `/admin/kb` 建/列/检索经 kb-serve（分机场景可模拟）；`/search` 带 rerank/planner 生效；绑定/observation 仍工作。
- [ ] 4.6 tasks.md 全 `[x]`；功能分支 `openspec archive platform-kb-serve-client`（同步 kb-admin-api spec）；**不扫 openspec/changes/archive/ 历史产物**；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
