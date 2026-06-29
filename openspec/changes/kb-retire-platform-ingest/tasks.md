## 1. 退连接器管理(store/sweep/端点/cron)

- [ ] 1.1 写/调整 integration 测试:退役后无 `/admin/kb/connectors/*` 端点;standalone 连接器配置(kb-service.yaml)仍可同步(见红/对照）
- [ ] 1.2 删 `kb_connector_sweep.py`、摘 server.py 的 `__kb_connector_sync_sweep__` cron 注册、删 config 的 `kb_connector_sweep_interval_seconds`
- [ ] 1.3 删 `kb_admin_api` 的 7 个连接器端点 + `kb_connector_store.py`；删 `_connector_settings` 等仅服务连接器端点的辅助
- [ ] 1.4 删 `test_kb_connector_admin.py`、`test_kb_connector_sweep.py`（测被退行为）；`git grep kb_connector_store|kb_connector_sweep|enqueue_connector_job` 确认无悬空引用；跑受影响层见绿

## 2. 退文档 import/sync + 显式 extraction 端点

- [ ] 2.1 写 integration 测试:退役后无 `POST /{kb_id}/documents`、`/{kb_id}/sync`、`/{kb_id}/extract-entities`；文档 list/preview/delete（读写 kb.db）仍在（见红/对照）
- [ ] 2.2 删上述端点 + `_enqueue_import_job`/`_enqueue_sync_directory_job`/`_wait_for_kb_ingest_job` 等仅服务这些端点的辅助；删 `test_kb_admin_api` 的 import/sync 用例
- [ ] 2.3 跑 kb-admin-api 相关 integration，确认保留端点（定义CRUD/list-lifecycle/检索/observation/绑定）全绿

## 3. 退 management.db 队列 + 平台 worker 接线 + drop 表

- [ ] 3.1 写 integration 测试:standalone 配置下 ingest → 自动 extraction → 图谱写入仍成立（走本地队列，不碰 management.db）（见红/对照）
- [ ] 3.2 `worker.py run_job` 删 import_document/sync_directory/connector_sync 的平台触发接线；standalone 用的 connector sync/extraction 分支保留；删 `test_kb_worker` 的 management.db 队列用例
- [ ] 3.3 新增前向 Alembic 迁移 drop `kb_connectors` / `kb_ingest_jobs` / `kb_connector_schedule_state`（迁移号取 head 下一个，勿硬编码）；跑迁移相关测试见绿
- [ ] 3.4 docker-compose `kb-worker` 接线调整为不依赖 management.db 队列（standalone/本地队列）；跑 3.1 见绿

## 4. 铁律守护 + 收尾

- [ ] 4.1 写测试断言**绑定/读链路零受损**:退役后 `/admin/kb/by-agent/{id}`、`/{kb_id}/agents` 仍工作；materialize 仍从 `agent_kbs` 生成 bindings；long_term_ctx 仍解析 kb_ids 检索（见红→绿）
- [ ] 4.2 `git grep` 残留:无对已删模块/端点/表的悬空引用；module-boundaries 护栏过；`knowledge_base` ✗→ platform、standalone 不连 management.db
- [ ] 4.3 跑 `make test-pr` + `make test-unit-ci`（含 76% 覆盖率关）+ `make test-integration-ci`，判"对照 main 基线无新增失败、覆盖率不破 76"（注:删被退测试后基线会变，确认新增失败=0；integration 并行 flaky 先 `-p no:randomly` 串行复核）
- [ ] 4.4 ruff format/check；`openspec validate kb-retire-platform-ingest` 通过；merge 后 `uv run alembic heads` 确认单 head
- [ ] 4.5 更新 `docs/capabilities/` + `docs/architecture/`:平台托管 KB ingest 已退役、单一模型=standalone KB 服务；升级须把平台连接器配置誊到 kb-service.yaml（非代码产物，人工确认后再 commit）
