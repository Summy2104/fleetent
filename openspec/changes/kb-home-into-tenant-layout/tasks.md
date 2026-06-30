> 每个实现任务前置其测试任务(TDD Hard Gate:先写测试见红 → 实现见绿)。最窄命令 `uv run pytest <file>::<test> -x -q`。

## 1. paths 派生层

- [ ] 1.1 写测试:`tests/unit/` 断言 `paths.tenant_kb_data_dir(t) == base/tenants/<t>/kb/data`,且 `tenant_kb_dir(t) == base/tenants/<t>/kb`(配置 home 不变)。见红。
- [ ] 1.2 实现:`paths.py` 新增 `tenant_kb_data_dir(tenant_id)`,返回 `tenant_kb_dir(tenant_id)/"data"`。见绿。

## 2. init-config 脚手架路径

- [ ] 2.1 改测试:`tests/unit/test_kb_service_init_config.py` 断言 `plan/apply_init_config` 的目标路径为 `tenants/<tenant>/kb/{kb-service.yaml,.env}`(取代 `kb-service/<tenant>/`),含显示串与 `next:` 提示文案。见红。
- [ ] 2.2 实现:`service_init_config.py` 的 `_tenant_home_dir` → `home_dir/"tenants"/tenant_id/"kb"`;同步 `plan` 的 `path` 展示串与 `main()` 的 `next:` 提示。见绿。

## 3. service_config 数据落位(`data.home` 不变,验证锚点位移)

- [ ] 3.1 改测试:`tests/unit/test_knowledge_service_config.py` 在 `tenants/<t>/kb/kb-service.yaml`(`data.home: ./data`)下断言 `data_dir()` 解析为 `tenants/<t>/kb/data`,`queue_database_url()` 指向 `kb/data/kb_ingest_queue.db`。见红(若现有断言绑旧路径)。
- [ ] 3.2 实现:确认 `service_config.load_kb_service_config` 相对解析逻辑无需改即满足;仅当断言要求时调整。模板 `kb-service.yaml.example` `data.home: ./data` 保持。见绿。

## 4. 删除 kb-worker tenant-less legacy 兜底

- [ ] 4.1 改测试:`tests/unit/test_kb_worker_config.py` 断言 `load_config()` 不再读 `$FLEETENT_HOME/kb-service/.env`(放置该文件不应被加载);canonical 路径仅经 `--config`。见红。
- [ ] 4.2 实现:`worker.py` 删除 `home_dir/"kb-service"/".env"` 兜底加载分支及其 docstring 引用。见绿。

## 5. tenant_router 读点下移至 kb/data/

- [ ] 5.1 改测试:`tests/integration/`(tenant_router 相关)断言 `ensure_tenant_kb_dir` 返回并建立 `tenants/<t>/kb/data/`,KB 关系库/向量库连接指向 `kb/data/kb.db`、`kb/data/kb_vectors.db`。见红。
- [ ] 5.2 实现:`tenant_router.py` 的 `ensure_tenant_kb_dir` 改用 `tenant_kb_data_dir`(经 `data_dir` 相对换算),KB 文件名常量落点随之进 `data/`。见绿。

## 6. node 挂载收窄 + _prepare_tenant_kb

- [ ] 6.1 改测试:`tests/integration/` node backend 用例断言 spawn agent 的 RO `--mount` `source` 指向 `tenants/<t>/kb/data/`(非整个 `kb/`),且 `kb/` 根的 `.env`/`kb-service.yaml` 不在挂载读面;`_prepare_tenant_kb` 在 `kb/data/` 下 migrate `kb.db` 并 touch `kb_vectors.db`。见红。
- [ ] 6.2 实现:`node/backend.py` 第二个 `_bind_mount` 改挂 `ensure_tenant_kb_dir(...)` 返回的 `kb/data/`;`_prepare_tenant_kb` 指 `kb/data/`。见绿。

## 7. standalone 服务端到端落位

- [ ] 7.1 改测试:`tests/integration/test_kb_standalone_service.py`(及 `test_packaged_config_templates.py`)断言 init-config → kb-worker/kb-serve 全链路在 `tenants/<t>/kb/` 下运作,库写入 `kb/data/`。见红。
- [ ] 7.2 实现:对齐上述代码改动后跑通;必要时修测试 fixture 的路径假设。见绿。

## 8. Makefile 与部署路径

- [ ] 8.1 改测试:`tests/unit/test_makefile_deploy_targets.py` 断言 kb-serve / kb-worker `--config` 与 init-config 目标指向 `$(FLEETENT_HOME)/tenants/default/kb/kb-service.yaml`。见红。
- [ ] 8.2 实现:`Makefile`(line ~186/201/204)路径更新为 `tenants/default/kb/`。见绿。

## 9. 文档同步(非代码产物,人工确认后提交)

- [ ] 9.1 改测试:`tests/integration/test_deployment_docs.py` 断言部署文档引用新布局路径(`tenants/<tenant>/kb/`)。见红。
- [ ] 9.2 更新 `docs/architecture/agent-home-layout.md`:已落地约束 5/6 + 目标布局改为 `tenants/<tenant>/kb/`(配置根 + `data/`)、node 挂 `kb/data/`。
- [ ] 9.3 更新 `docs/architecture/data-model.md`、`docs/deployment/compose.md`、`docs/operations/{pilot-runbook,pilot-install-checklist,local-managed-stack}.md`、`docs/capabilities/{knowledge-base,config-management}.md` 中的 `kb-service/<tenant>/` 路径引用。
- [ ] 9.4 跑 `test_deployment_docs` 见绿。

## 10. 收尾验证

- [ ] 10.1 全量 grep 确认无残留 `kb-service/` **目录**路径构造(区分:配置文件名 `kb-service.yaml` / CLI 命令 / `provider="kb-service"` 保留)。
- [ ] 10.2 `make test-pr` + `make test-integration-ci` 全绿;`scripts/check_module_boundaries.py` 通过(KB/node 不 import platform)。
