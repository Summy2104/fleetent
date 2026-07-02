## Context

kb-serve/worker 现为每租户一套（config 单 tenant_id、serve 单租户 403、worker 单队列）。存储层 `TenantRouter` 本已多租户（`tenant_scope(tenant_id)` 开任意租户 `tenants/<t>/kb/data/`）。目标：单机多租户中心 KB 服务，平台+agent 皆 HTTP 客户端，租户经 principal 路由。数据仍每租户 SQLite（隔离在数据层，进程共享）。

## Goals / Non-Goals

**Goals**
- 一套 kb-serve + 一套 kb-worker 服务本机所有租户。
- 两层 config：本机服务 config（含共享 service-key + 全机一个 embedding）+ per-tenant connectors/secret。
- 运行时按 `principal.tenant_id` / job.tenant_id 路由；`--tenant` 可选锁单租户。

**Non-Goals**
- embedding per-tenant 覆盖（全机一模型；未来选项）。
- agent→HTTP provider（D）、平台→客户端（B）。
- 改数据布局/隔离、改单写者纪律（内容写仍唯一 worker）。

## Decisions

**D1：两层 config。**
- 本机 `FLEETENT_HOME/kb-service.yaml`：`service`(host/port/**service_key_ref 共享**) + `embedding` + `rerank` + `extraction`(model) + `retrieval`/`chunking` 默认。kb-serve 与 kb-worker 都读它。
- per-tenant 残余：`tenants/<t>/kb/` 下**只留 connectors 定义 + `.env` secret**。为避免与本机 `kb-service.yaml` 同名混淆,per-tenant 文件**改名 `connectors.yaml`**（内容=原 kb-service.yaml 的 `connectors` 段）。`.env` 不变。
- `service_config.py`：加 `load_host_service_config(home)` 与 `load_tenant_connectors(home, tenant_id)`;`discover_tenants(home)` = 扫 `tenants/*/kb/data/` 有 kb.db 者。

**D2：kb-serve 多租户路由。**
启动读本机 config（无单租户 pin）。`_require_authorized_principal`：验共享 service-key（传输）后,以 `principal.tenant_id` 为路由键——经 `TenantRouter.tenant_scope(principal.tenant_id)` 取该租户 KB db 执行。删除"principal.tenant_id != config.tenant_id → 403"的单租户硬校验。per-request 解析租户 scope（TenantRouter 已缓存,廉价）。`--tenant` 存在时仍锁该租户（非该租户 principal → 403,即旧行为）。

**D3：kb-worker 轮询多队列 + per-tenant secret 按需。**
worker 循环：`discover_tenants(home)` → 对每租户 `tenants/<t>/kb/data/kb_ingest_queue.db` claim job → 处理时按 job.tenant_id 用 `TenantRouter` 写该租户 KB、并**按需加载该租户 `tenants/<t>/kb/.env` + connectors.yaml**（connector_sync job 才需 secret）。轮询顺序与公平性:简单轮转即可(job 量小)。`--tenant` 锁则只 drain 该租户队列。单写者不破:worker 仍是各租户内容/向量的唯一写者。

**D4：全机一个 embedding（已拍）。**
本机 config 一个 `embedding` 段,全租户 KB 共用。与 per-KB embedding 身份校验(Change B)相容——所有 KB 必须同模型,校验会挡住不一致。约束写入 spec:换本机 embedding 模型需 reindex 全 KB。per-tenant 覆盖不做(未来选项)。

**D5：共享 service-key（已拍）。**
一把 host 级 service_key_ref 落本机 config。传输层门槛;真实身份/租户由可信 principal(node/forwarder/平台注入)承载。per-tenant service-key 退役。

**D6：部署一套进程。**
Makefile `kb-serve`/`kb-worker` 目标改为读本机 `FLEETENT_HOME/kb-service.yaml`、各起一个;docker-compose 同理(去掉 per-tenant 实例概念)。`kb init-config` 生成本机 config + 为已存在租户生成 `connectors.yaml` stub。

## Risks / Trade-offs

- **进程级隔离下降**：一个进程持所有租户 connector secret(按需加载可缩短驻留)、一崩全挂。→ 接受(单机多租户、单组织场景);`--tenant` 锁给强隔离退路。
- **worker 轮询公平性/延迟**：多租户共一 worker,单租户大 job 可能占用。→ 简单轮转 + job 量评估;真需要再加并发/优先级(本 change 不做)。
- **换 embedding 模型的代价**：全机一模型,换 = reindex 全 KB。→ 写入 spec 明示;有 `kb reindex` 兜底。
- **per-tenant 文件改名 connectors.yaml**：牵动 docs/示例;未上线,init-config 直接出新布局,无迁移。
- **worker 发现新租户的时效**：轮询循环每轮重扫 `tenants/`,新租户 kb home 一建即被纳入,无需重启。

## Migration Plan

无数据迁移(布局不变)。config 布局重构:本机 config 上移 + per-tenant 瘦成 connectors.yaml,由 `kb init-config` 生成。部署改为一套进程。回滚 = revert + 用 `--tenant` 退回单租户运行。

## Open Questions

无(embedding 全机一模型、共享 service-key、per-tenant 只留 connector 均已拍;worker 并发/优先级为未来增强,不在本 change)。
