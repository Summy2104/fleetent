## Why

KB 独立部署线落地后,standalone kb-service 的**数据布局**和 **env/config key** 留了两类收尾债:

1. **数据布局照搬了 agent-home 的赘余嵌套 + 队列放错层**。standalone 落盘是
   `data.home/tenants/<t>/kb/{kb.db,kb_vectors.db}` + `data.home/kb_ingest_queue.db`(根):
   - `/kb/` 这层是 agent-home 用来跟 `agents/` 并列区分的——standalone **没有 agent**,旁边空无一物,纯赘余;
   - 队列在 `data.home` 根,多租户(每租户一进程,各起一进程)会**共抢同一个 SQLite 队列文件** → 单写者争用;
   - 默认 `data.home: ./data/kb-service`,配置又在 `<HOME>/kb-service/` 下 → 落到 `kb-service/data/kb-service/` **双 kb-service** 套娃。

2. **env/config key 自创了一套 `KB_*`,与全项目 `FLEETENT_<域>_<字段>` + `*_env` 引用范式分叉,且有死 key**:
   - `KB_SERVICE_KEY` / `KB_SHARED_GOOGLE_DRIVE`(JSON blob)/ `KB_CONN_*` 三套子命名,不合 `FLEETENT_*`;Google Drive 凭据塞成 JSON,而 `KBConnectorSection` schema 本就支持 `access_token_env/client_id_env/...` 粒度字段(`service_config.py:78-83`),example 没用;
   - **死 key**:`KB_EMBEDDING_API_KEY` / `KB_EXTRACTION_API_KEY` 无人读取。根因更深——`serve.py` **零引用** `config.embedding`,该 section 只在 `service_config.py:198` 被校验、**从未接进 embedding backend**;worker 又走另一套 `FLEETENT_KB_WORKER_EMBEDDING_*` env。`EmbeddingSettings`(`config.py:79`)本就有 `api_key_env`,只是 KB section 没这字段、也没接线。

## What Changes

### A. 数据布局拍平(形态 2a:保留租户扇出、砍 `/kb/`、队列下沉)

standalone kb-service 落盘改为:

```
data.home/tenants/<tenant_id>/
├── kb.db
├── kb_vectors.db
└── kb_ingest_queue.db          # 队列下沉进租户子树,每进程独占
```

- 砍掉 `/kb/` 中间层(standalone 无 agent,无需与 `agents/` 区分)。
- 队列从 `data.home` 根**下沉**到 `tenants/<tenant_id>/`,修掉多租户共抢队列。
- 默认 `data.home` 从 `./data/kb-service` 改为 `./data`(消除双 kb-service 套娃)。
- **每租户一进程不变**:多租户 = 多进程共享一个 data root,各绑自己的 `tenants/<t>/` 子树、各自队列;单 active DB 全局态依旧安全。
- **不碰嵌入式 `SQLiteTenantBackend`**(agent-home 的 `tenants/<t>/kb/` 旁边真有 `agents/`,保留)。standalone 用独立的 flat 解析(serve/worker 各自的 `_tenant_router` 接缝),只服务 standalone。

### B. env/config 对齐项目范式 + 接死 key

- **service key**:`service_key_ref: env:FLEETENT_KB_SERVICE_KEY`。
- **connectors**:改用粒度 `*_env` 字段(`access_token_env: FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN`、`api_token_env: FLEETENT_CONFLUENCE_TOKEN`、`username_env: FLEETENT_CONFLUENCE_USERNAME` 等),env 名全 `FLEETENT_*`;**去掉 JSON blob 凭据**。镜像平台时代 `.env.example` 的 KB 段。
- **embedding/extraction**:给 `KBEmbeddingSection` / `KBExtractionSection` **加 `api_key_env` 字段**,把 kb-service.yaml 的 embedding/extraction section 接成 `EmbeddingSettings`(endpoint/model/dimensions/api_key_env)的**单一来源**,serve 与 worker 共用——替掉 worker 那套 `FLEETENT_KB_WORKER_EMBEDDING_*` env;env 用 `FLEETENT_KB_EMBEDDING_API_KEY` / `FLEETENT_KB_EXTRACTION_API_KEY`。**死 key 由此接活**。
- **boot 校验**扩展:embedding/extraction 若配了 `api_key_env`,缺失则启动即失败(与现有 connector credential_ref 校验同款 fail-fast)。
- 重写 `kb-service.yaml.example` + `kb-service.env.example`。

## Capabilities

### Modified Capabilities
- `kb-standalone-ingest`:standalone 数据布局拍平(`tenants/<t>/{kb.db,kb_vectors.db,kb_ingest_queue.db}`,队列下沉);boot 校验覆盖 embedding/extraction key。
- `knowledge-service-config`:standalone kb-service 的 service key / connectors / embedding / extraction 全部走项目 `FLEETENT_*` + `*_env` 引用范式;embedding/extraction 经 `api_key_env` 引用密钥。

## Impact

- **owning package**:`knowledge_base/`(serve.py / worker.py / service_config.py / kb-service 模板)+ `vector_store` embedding 接线(消费已存在的 `EmbeddingSettings.api_key_env`)。
- **public API surface**:无 HTTP/CLI 签名变化;kb-service.yaml schema 加 `embedding.api_key_env` / `extraction.api_key_env` 字段(向后兼容,默认空)。
- **owned tables**:无新增表;standalone 物理文件**换位置**(`tenants/<t>/kb/` → `tenants/<t>/`,队列下沉)。
- **config namespace**:`kb-service.yaml` + `kb-service/.env`;env 名迁到 `FLEETENT_*`。
- **cross-module 依赖**:不新增;不碰 platform;不碰嵌入式 `SQLiteTenantBackend`。
- **migration / shim**:standalone KB 数据是**物理文件位置变更**,非 schema 迁移。KB 独立线刚落地、无生产数据;dev `.fleetent-dev` 若已有 standalone KB 文件,需一次性按新布局移动(docs 注明);worker 的旧 `FLEETENT_KB_WORKER_EMBEDDING_*` env 退役(boot 文档同步)。
- **解耦基线**:不影响——standalone 仍可在无 platform / management.db 不存在下 ingest+检索。
- **测试**:`make test-pr` + `make test-integration-ci` 全绿;新增 standalone 布局解析 + embedding key 接线 + 配置校验单测。
