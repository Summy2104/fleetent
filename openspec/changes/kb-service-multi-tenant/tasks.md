# Tasks: kb-service-multi-tenant

> kb-serve/worker 单机多租户化。数据仍每租户 SQLite（隔离不动），共享的是进程。默认多租户，`--tenant` 可选锁。
> 全机一个 embedding 模型；共享 service-key 落本机 config。单写者纪律不破（内容/向量写仍唯一 worker）。
> TDD Hard Gate：测试在实现前，最窄命令红→绿。

## 1. 两层 config 模型 + 租户发现（service_config.py）

- [ ] 1.1 [test-red] 测 `service_config`：`load_host_service_config($FLEETENT_HOME/kb-service.yaml)` 解析 service(host/port/共享 service_key_ref)+embedding+rerank+extraction+retrieval/chunking；`load_tenant_connectors(home, tenant)` 读 `tenants/<t>/kb/connectors.yaml`+`.env`；`discover_tenants(home)` 扫 `tenants/*/kb/data/kb.db`。跑 `uv run pytest tests/*/test_kb_service_config* -x -q` → 见红。
- [ ] 1.2 [impl] 实现上述加载/发现函数；本机 config 不再含 tenant_id/connectors；per-tenant 只剩 connectors。保留旧单文件解析路径供 `--tenant` 锁模式复用（或统一）。跑 → 见绿。

## 2. kb-serve 多租户路由

- [ ] 2.1 [test-red] 集成测 kb-serve（stub embedding）：默认模式下，带 `principal.tenant_id=A` 请求路由到 A 的 KB、带 B 路由到 B（`/search` + `/kb` 管理端点均按 principal 路由）；删除"principal≠config.tenant_id 一律 403"；`--tenant A` 锁定时 B 的 principal 被 403。跑 → 见红。
- [ ] 2.2 [impl] `serve.py`：启动读本机 config（不 `_bootstrap_runtime(单tenant)`）；每请求经 `_require_authorized_principal` 验共享 service-key 后，以 `principal.tenant_id` 经 `TenantRouter.tenant_scope(...)` 解析该租户 kb_db/vector_backend 执行；加 `--tenant` 锁参数。跑 → 见绿。

## 3. kb-worker 多租户

- [ ] 3.1 [test-red] 集成测：worker 默认轮询 A、B 两租户队列各自认领、按 job.tenant_id 写各自 KB 互不串写；处理 A 的 connector_sync 只加载 A 的 `.env`；新建租户 C 下一轮被纳入；`--tenant A` 只 drain A。跑 → 见红。
- [ ] 3.2 [impl] `worker.py`：主循环 `discover_tenants` → 轮询各租户 `kb_ingest_queue.db` → 按 job.tenant_id 经 TenantRouter 写 + 按需 `load_tenant_connectors`；本机 config 提供 embedding/extraction；加 `--tenant` 锁。跑 → 见绿。

## 4. init-config 新布局 + 部署

- [ ] 4.1 [impl] `service_init_config.py`：`kb init-config` 生成本机 `$FLEETENT_HOME/kb-service.yaml`（从根 example）+ 为已存在租户 scaffold `tenants/<t>/kb/connectors.yaml`+`.env`。
- [ ] 4.2 [impl] example 模板：`kb-service.yaml.example` 改为**本机服务级**（去 tenant_id/connectors，留 service/embedding/rerank/extraction/retrieval/chunking）；新增 `connectors.yaml.example`（per-tenant 连接器）。`kb-service.env.example` 保留（连接器 secret）。
- [ ] 4.3 [impl] `Makefile`：`kb-serve`/`kb-worker` 目标改读本机 `$(FLEETENT_HOME)/kb-service.yaml`、各起**一个**（去每租户实例）；`dev-bootstrap` 生成本机 config。`docker-compose.yml`：kb-serve/kb-worker 各一个服务实例（多租户）。
- [ ] 4.4 [impl] docs 同步（operations/deployment/capabilities）：一套进程 + 两层 config + `--tenant` 锁说明；**不扫 openspec/changes/archive/ 历史产物**。

## 5. 收尾门禁（全绿才算完）

- [ ] 5.1 边界护栏：`PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py`；serve/worker 无 platform import；数据仍每租户 SQLite（未引入跨租户共享库）。
- [ ] 5.2 `openspec validate kb-service-multi-tenant --strict`
- [ ] 5.3 `uv run mypy src`
- [ ] 5.4 `make test-pr` + `make test-integration-ci`，判据"对照 main 基线无新增失败"。
- [ ] 5.5 手验：本机 config 起一套 kb-serve+kb-worker；建两租户 KB（`kb create` × 2，不同 tenant）；各自 `kb ingest`；一个 kb-serve 端点带不同 principal.tenant_id 检索命中各租户内容；`--tenant` 锁模式验隔离。
- [ ] 5.6 tasks.md 全 `[x]`；功能分支 `openspec archive kb-service-multi-tenant`（同步 kb-standalone-ingest + kb-read-service + kb-ingest-worker 三 spec）；commit（含 Co-Authored-By 签名）+ 推分支；**不 merge main，等 Randy 定夺**。
