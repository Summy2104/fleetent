## 背景与接缝

KB 独立部署线刚落地(`kb-read-service` / `kb-standalone-ingest` / `kb-retire-platform-ingest` 等)。本 change 收两类收尾债,不引入新能力。

### A. standalone 数据布局(Design I)

**现状接缝**:
- `serve.py` / `worker.py` 的 `_tenant_router(data_dir)` 已走 standalone flat backend,但仍把 `tenant_id` 编进 `data_dir/tenants/<t>/{kb.db,kb_vectors.db}` 这一层——这是过渡态 2a。
- 队列经 `service_config.queue_database_url()`(`service_config.py:101`)落 `data_dir/kb_ingest_queue.db`(**根**)。

**目标接缝**:
- standalone 用**独立的 flat 解析**(不走共享 `SQLiteTenantBackend`),但 flat 的根直接就是**当前 tenant home 的 `data/`**:`data_dir/{kb.db,kb_vectors.db}`。`tenant_id` 只留在 `KbScope.tenant_id` 元数据,**不参与路径**。
- `queue_database_url()` 直接落 `data_dir/kb_ingest_queue.db`。
- `fleetent kb-service init-config` 改为**每租户 home**脚手架:`kb-service/<tenant>/kb-service.yaml` + `.env`;支持 `--tenant <id>`(默认 `default`)。
- `kb-service.yaml.example` 默认 `service.tenant_id: default`;`data.home: ./data` 保持不变。

**为何不碰嵌入式**:嵌入式 KB 文件由 agent 进程 in-process(LocalKnowledgeProvider)读,路径来自 `paths.tenant_kb_dir` + `SQLiteTenantBackend`,与 standalone(HttpKnowledgeProvider 经网络)是两条独立物理路径,互不影响。

**多租户语义(验收锚点)**:每租户一进程,各进程 `service.tenant_id` 不同、绑各自 `kb-service/<tenant>/data/`、各自队列文件;tenant 身份用于鉴权/审计 scope,不是路径分量 → 单 active DB 全局态安全。

### B. env / config 范式对齐 + 接死 key

**死 key 根因**:`serve.py` 零引用 `config.embedding`;该 section 只在 `service_config.py:198` 被校验 endpoint 非空,**从未翻译成 `EmbeddingSettings` 接进 backend**。worker 走另一套 `FLEETENT_KB_WORKER_EMBEDDING_*` env(`worker.py:60-62`)。`EmbeddingSettings`(`config.py:71-79`)已有 `endpoint/model/dimensions/api_key_env`,`_HttpEmbeddingBackend`(`vector_store/embeddings.py:50-68`)已消费 `api_key_env`。

**修法**:
- `KBEmbeddingSection` 加 `api_key_env: str = ""`;`KBExtractionSection` 加 `api_key_env: str = ""`。
- 加一个 `KBEmbeddingSection → EmbeddingSettings` 的翻译(endpoint/model/dimensions/api_key_env),在 **serve 与 worker boot** 各自接成单一来源,替掉 worker 的 `FLEETENT_KB_WORKER_EMBEDDING_*` env 路径。
- boot 校验(`kb-standalone-ingest` Boot validation)扩展:embedding/extraction 的 `api_key_env`(若设)所指 env 缺失则启动失败。
- 模板 `kb-service.{yaml,env}.example` 重写:`FLEETENT_*` 命名、connector 粒度 `*_env`、去 JSON blob。

## 决策

- **2a vs Design I**:改判为 Design I。standalone 已经是每租户一进程,把 config + env + data 一起收进 `kb-service/<tenant>/` 更符合 operator 心智;`tenant_id` 回到逻辑身份,不再硬编码进 sqlite 文件路径。
- **不合并跨租户同类 DB**:每租户物理独立(数据主权 + 物理隔离 + 与每租户一进程/单 active DB 全局态吻合);跨租户合库仅 SaaS 级并发才回本,本项目明确非该形态。
- **data.home 语义收窄**:仅表示 sqlite 本地文件后端的存储根。未来若接 PG/Qdrant,各自增加独立 storage locator(dsn/schema、url/collection),而不是重绘 `data.home`。
- **embedding 单一来源 = kb-service.yaml**:退役 worker 的独立 `FLEETENT_KB_WORKER_EMBEDDING_*` env,避免"两处配 embedding"再分叉。

## 风险与缓解

- **物理文件位置变更**(非 schema 迁移):KB 独立线刚落地、无生产数据;dev `.fleetent-dev` 若已有 standalone KB 文件,docs 注明一次性手动移到新布局。不写迁移框架(这是文件搬位,非 user_version 升级)。
- **worker embedding env 退役**:若有脚本/compose 依赖 `FLEETENT_KB_WORKER_EMBEDDING_*`,boot 文档与 compose 模板同步改为 kb-service.yaml embedding section。
- **seam 纪律回归**:除 sqlite 后端实现内部,其它调用方不许 hardcode `.../data/kb.db` 文件路径。通过现有 router / provider / service_config 接缝保持后端无关,避免未来 PG/Qdrant 时再次 repaint。
- **回归边界**:嵌入式 `SQLiteTenantBackend` 零改动;护栏 `make test-pr` + integration 全绿;新增 standalone 布局解析、队列落点、embedding 接线、boot 校验单测各自见红→见绿。
