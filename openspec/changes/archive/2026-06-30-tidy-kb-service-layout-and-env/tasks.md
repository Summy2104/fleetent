## 1. standalone 数据布局拍平(2a)

- [x] 1.1 测试先行:写 standalone tenant 路径解析的单测——断言 `kb.db` / `kb_vectors.db` 落 `data.home/` 直属层级;`tenant_id` 仅保留在 scope 元数据、不入路径。`uv run pytest <file>::<test> -x -q` 见红
- [x] 1.2 实现 standalone flat 解析(`tenant_router` 增 flat 后端变体或 serve/worker 内联),`serve.py` / `worker.py` 的 `_tenant_router` 接缝改用之;**不碰 `SQLiteTenantBackend` 嵌入式语义**。见绿
- [x] 1.3 测试先行:断言 `queue_database_url()` 落 `data.home/kb_ingest_queue.db`(纯平)。见红
- [x] 1.4 实现 `service_config.queue_database_url()` 直接取 `data_dir()/kb_ingest_queue.db`。见绿
- [x] 1.5 测试先行:多租户隔离——两个不同 tenant home(`kb-service/<tenant>/data`)互不共享,各自解析到自己的 `data/{kb.db,kb_vectors.db,kb_ingest_queue.db}`。见红→实现已满足则补断言→见绿
- [x] 1.6 `service_init_config` 改为每租户 home:`kb-service/<tenant>/kb-service.yaml` + `.env`;支持 `--tenant <id>`(默认 `default`),并把 yaml 的 `service.tenant_id` 写成该 tenant。`kb-service.yaml.example` 默认 `tenant_id: default`;`data.home: ./data` 保持

## 2. embedding/extraction api_key_env 接线(补死 key)

- [x] 2.1 测试先行:`KBEmbeddingSection` / `KBExtractionSection` 含 `api_key_env` 字段且能解析。见红
- [x] 2.2 实现:两 section 加 `api_key_env: str = ""`。见绿
- [x] 2.3 测试先行:`KBEmbeddingSection → EmbeddingSettings` 翻译把 endpoint/model/dimensions/api_key_env 正确带入;serve 与 worker boot 用它作单一来源(替 `FLEETENT_KB_WORKER_EMBEDDING_*`)。见红
- [x] 2.4 实现翻译 + serve/worker 接线;退役 worker 的 `FLEETENT_KB_WORKER_EMBEDDING_*` env 读取。见绿
- [x] 2.5 测试先行:embedding 请求头携带 `api_key_env` 指向的密钥(复用 `_HttpEmbeddingBackend` 路径,`respx`/mock)。见红→见绿

## 3. boot 校验扩展

- [x] 3.1 测试先行:embedding/extraction 配了 `api_key_env` 但 env 缺失 → 启动即失败并报缺项;齐全则成功。见红
- [x] 3.2 实现 boot 校验覆盖 embedding/extraction `api_key_env`。见绿

## 4. 模板与文档

- [x] 4.1 重写 `kb-service.env.example`:`FLEETENT_KB_SERVICE_KEY` / `FLEETENT_GOOGLE_DRIVE_*` / `FLEETENT_CONFLUENCE_*` / `FLEETENT_KB_EMBEDDING_API_KEY` / `FLEETENT_KB_EXTRACTION_API_KEY`;去 `KB_SHARED_*` JSON blob 与 `KB_CONN_*`
- [x] 4.2 重写 `kb-service.yaml.example`:`service_key_ref: env:FLEETENT_KB_SERVICE_KEY`;connector 用粒度 `*_env`;`embedding.api_key_env` / `extraction.api_key_env`;`data.home: ./data`
- [x] 4.3 更新部署/boot 文档:standalone 布局示意改为 `kb-service/<tenant>/{kb-service.yaml,.env,data/{kb.db,kb_vectors.db,kb_ingest_queue.db}}`;说明 worker `FLEETENT_KB_WORKER_EMBEDDING_*` 退役 + dev 旧 standalone KB 文件一次性迁移说明;compose / Makefile 默认路径同步到 `kb-service/default/`

## 5. 收尾门禁

- [x] 5.1 `openspec validate tidy-kb-service-layout-and-env --strict` 通过
- [x] 5.2 `make test-pr` 全绿(含改动文件 ruff + 层边界)
- [x] 5.3 `make test-integration-ci` 零新增失败
- [x] 5.4 `PYTHONPATH=src:. uv run python scripts/check_module_boundaries.py` 通过(未碰 platform / 嵌入式 backend)
- [x] 5.5 所有 tasks.md checkbox 标 `[x]`
