## Why

现在 kb-serve / kb-worker 是**每租户一套进程**（`kb-service.yaml` 单 `service.tenant_id`；serve 绑一个租户、principal 跨租户即 403；worker 只 drain 一个租户队列）。运维上"每租户起一套"很麻烦。

目标拓扑（已定）：**KB 单机多租户中心服务**——一套 kb-serve + 一套 kb-worker 服务本机所有租户；平台（可异机）与 agent node（多机）都是它的 HTTP 客户端，租户靠 `principal.tenant_id` 路由。存储层（`TenantRouter`）本已多租户，单租户是"进程/配置/鉴权"这层钉的。本 change 把这层解开——**数据仍每租户独立 SQLite，隔离不丢，共享的只是进程**。

这是 KB 收口程序的**枢纽**（前置 A=kb-serve 完整 API 已落地；后续 D=agent 走 HTTP、B=平台退客户端，均在 C 之后）。

## What Changes

**两层 config（核心）：**
- **本机服务级 config** `FLEETENT_HOME/kb-service.yaml`（一份，kb-serve 与 kb-worker 都读）：`service`(host/port/**共享 service_key_ref**) + `embedding`（**全机一个模型**）+ `rerank` + `extraction`(model) + `retrieval`/`chunking` 默认。
- **per-tenant config**（仍在 `tenants/<t>/kb/`，瘦成只剩 connectors + `.env` secret）：kb-worker 处理某租户 job 时**按需加载**该租户 connector/secret。
- 租户发现：扫 `FLEETENT_HOME/tenants/*/kb/data/`（有 kb home 即存在，动态）。

**kb-serve 多租户：** 启动读本机 config（不再绑单租户）；鉴权 = 共享 service-key（传输）+ 可信 `principal.tenant_id`（路由/授权），跨租户不再一律 403，而是**路由到该租户** KB（经 `TenantRouter`）；所有端点（search / /kb 管理 / status / evaluations）按 principal 租户路由。

**kb-worker 多租户：** **轮询所有租户的 per-tenant 队列**（扫 `tenants/`，各开 `kb_ingest_queue.db`）；每 job 按其 tenant 加载该租户 connector secret 并写该租户 KB。

**保留单租户模式：** `--tenant <id>` 可选**锁单租户**（强隔离/调试），默认多租户。

**部署：** Makefile / docker-compose 从"每租户一套"改为**一套** kb-serve + 一套 kb-worker；`kb init-config` 生成本机 config + per-tenant connector stub；docs 同步。

**不做：** embedding per-tenant 覆盖（全机一模型，未来选项）；agent 走 HTTP provider（Change D）；平台退 kb-serve 客户端（Change B）；数据布局/隔离不动（仍每租户 SQLite）。

## Capabilities

### New Capabilities
（无）

### Modified Capabilities
- `kb-standalone-ingest`：从"每租户一进程（单 service.tenant_id）"改为"**单机多租户服务**"——两层 config（本机服务 config + per-tenant connectors）、租户运行时路由（默认全租户，`--tenant` 可选锁）、全机一个 embedding 模型；每租户数据 SQLite 零共享不变。
- `kb-read-service`：kb-serve 多租户——鉴权改为共享 service-key + 按 `principal.tenant_id` 路由（不再单租户 403），端点按 principal 租户经 `TenantRouter` 解析对应租户 KB。
- `kb-ingest-worker`：kb-worker 多租户——轮询所有租户 per-tenant 队列、按 job 租户加载 connector secret 并写对应租户 KB（单写者纪律不变：内容/向量写仍唯一经 worker）。

## Impact

- **代码**：`knowledge_base/service_config.py`（两层 config 加载 + 租户发现）；`serve.py`（多租户路由 + 鉴权）；`worker.py`（轮询多队列 + per-tenant secret 按需加载）；`service_init_config.py`（生成新布局）。
- **部署**：`Makefile` / `docker-compose.yml`（一套进程）；docs（operations/deployment）。
- **spec**：kb-standalone-ingest / kb-read-service / kb-ingest-worker 三 delta。
- **无 DB schema 变更、无迁移**（数据布局不变，每租户 SQLite 原地）；**无 wire 破坏**（principal 已带 tenant_id）。
- 兼容：`--tenant` 锁保留单租户/standalone 用法；现有 per-tenant `kb-service.yaml` 未上线，`kb init-config` 按新布局重生成（本机 config + per-tenant connector stub），不做数据迁移。
- 依赖：本 change 是 D（agent→HTTP）、B（平台→客户端）的前置枢纽。
