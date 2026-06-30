## 1. standalone 数据布局拍平(2a)

- [ ] 1.1 测试先行:写 standalone tenant 路径解析的单测——断言 `kb.db` / `kb_vectors.db` 落 `data.home/tenants/<tenant_id>/`(**无 `kb/` 中间层**)。`uv run pytest <file>::<test> -x -q` 见红
- [ ] 1.2 实现 standalone flat 解析(`tenant_router` 增 flat 后端变体或 serve/worker 内联),`serve.py` / `worker.py` 的 `_tenant_router` 接缝改用之;**不碰 `SQLiteTenantBackend` 嵌入式语义**。见绿
- [ ] 1.3 测试先行:断言 `queue_database_url()` 落 `data.home/tenants/<service.tenant_id>/kb_ingest_queue.db`(**下沉、非 data.home 根**)。见红
- [ ] 1.4 实现 `service_config.queue_database_url()` tenant-aware。见绿
- [ ] 1.5 测试先行:多租户隔离——两个不同 `service.tenant_id` 解析到不同 `tenants/<t>/` 子树与各自队列文件,零共享。见红→实现已满足则补断言→见绿
- [ ] 1.6 `kb-service.yaml.example` 默认 `data.home: ./data`(去双 kb-service);改 `service_init_config` 相关断言/快照(如有)

## 2. embedding/extraction api_key_env 接线(补死 key)

- [ ] 2.1 测试先行:`KBEmbeddingSection` / `KBExtractionSection` 含 `api_key_env` 字段且能解析。见红
- [ ] 2.2 实现:两 section 加 `api_key_env: str = ""`。见绿
- [ ] 2.3 测试先行:`KBEmbeddingSection → EmbeddingSettings` 翻译把 endpoint/model/dimensions/api_key_env 正确带入;serve 与 worker boot 用它作单一来源(替 `FLEETENT_KB_WORKER_EMBEDDING_*`)。见红
- [ ] 2.4 实现翻译 + serve/worker 接线;退役 worker 的 `FLEETENT_KB_WORKER_EMBEDDING_*` env 读取。见绿
- [ ] 2.5 测试先行:embedding 请求头携带 `api_key_env` 指向的密钥(复用 `_HttpEmbeddingBackend` 路径,`respx`/mock)。见红→见绿

## 3. boot 校验扩展

- [ ] 3.1 测试先行:embedding/extraction 配了 `api_key_env` 但 env 缺失 → 启动即失败并报缺项;齐全则成功。见红
- [ ] 3.2 实现 boot 校验覆盖 embedding/extraction `api_key_env`。见绿

## 4. 模板与文档

- [ ] 4.1 重写 `kb-service.env.example`:`FLEETENT_KB_SERVICE_KEY` / `FLEETENT_GOOGLE_DRIVE_*` / `FLEETENT_CONFLUENCE_*` / `FLEETENT_KB_EMBEDDING_API_KEY` / `FLEETENT_KB_EXTRACTION_API_KEY`;去 `KB_SHARED_*` JSON blob 与 `KB_CONN_*`
- [ ] 4.2 重写 `kb-service.yaml.example`:`service_key_ref: env:FLEETENT_KB_SERVICE_KEY`;connector 用粒度 `*_env`;`embedding.api_key_env` / `extraction.api_key_env`;`data.home: ./data`
- [ ] 4.3 更新部署/boot 文档:standalone 布局示意改为 `tenants/<t>/{kb.db,kb_vectors.db,kb_ingest_queue.db}`;说明 worker `FLEETENT_KB_WORKER_EMBEDDING_*` 退役 + dev 旧 standalone KB 文件一次性迁移说明;compose 模板(若引用旧 env)同步

## 5. 收尾门禁

- [ ] 5.1 `openspec validate tidy-kb-service-layout-and-env --strict` 通过
- [ ] 5.2 `make test-pr` 全绿(含改动文件 ruff + 层边界)
- [ ] 5.3 `make test-integration-ci` 零新增失败
- [ ] 5.4 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过(未碰 platform / 嵌入式 backend)
- [ ] 5.5 所有 tasks.md checkbox 标 `[x]`
