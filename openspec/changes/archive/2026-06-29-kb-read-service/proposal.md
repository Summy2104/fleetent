## Why

`kb-http-provider`(Slice ①)给了 agent 的 HTTP client + wire 协议,但**没有 server 实现这份协议**——agent 还没有可指向的远程 KB 检索端点。本 change(Slice ②a)建 **KB 读服务**:一个精简 HTTP 服务,实现 Slice ① 的 wire 协议,让"agent 经 HttpKnowledgeProvider 读远程 KB"端到端跑通。

scope 严格限定为**读**:服务读本地 `tenants/<t>/kb/`(由现有 ingest 写,不改);**不**搬迁 ingest worker / 队列 / connector secret——那是 ②b(风险集中处)。利用已定的"每租户一进程"(选项 A):服务 boot 时绑定其租户、`set_database` 一次,**不触碰检索核的全局状态、无需去全局重构**。

## What Changes

- **新建 KB 读服务**(精简 FastAPI):实现 Slice ① wire 协议——`POST /search` body `{principal:{user_id,tenant_id}, query, kb_ids, limit}` → `{chunks: [KnowledgeChunk JSON]}`。
- **boot 时按租户绑定**:服务启动参数/配置带 `tenant_id`;boot 时 `tenant_scope(tenant)` → `kb_runtime.set_database` / `set_vector_backend` 一次(per-tenant 进程,并发请求同租户、无 race)。
- **请求处理**:decode `X-Fleetent-Principal` → 校验 `principal.tenant_id` == 服务租户(不符拒绝)→ 调 `knowledge_base.search`(显式 `mode`,服务级默认 `hybrid`;`kb_ids`/`limit` 来自请求)→ 返回 chunks。`plan_knowledge_search`/`graph_search` 同理可选。
- **鉴权**:Bearer service key + `X-Fleetent-Principal`(复用 `identity.decode_ingress_principal`)。
- **入口**:`fleetent kb serve`(`main()` + uvicorn,照 `kb-worker` 范式)。

不改变:`knowledge_base` 检索核(只显式调其 public API);现有 ingest(worker/队列/secret 一字不动);LocalKnowledgeProvider 与单机嵌入式路径;Slice ① 的 client 与协议。

## Capabilities

### New Capabilities
- `kb-read-service`: 一个实现 knowledge wire 协议的 per-tenant HTTP 读服务,经 `tenant_scope` 注入读本租户 `kb/`,Bearer + Principal 鉴权,服务级检索 policy。

### Modified Capabilities
<!-- 无 -->

## Impact

- **owning package**:`fleetent.knowledge_base`(新增服务入口模块,如 `knowledge_base/serve.py`;FastAPI 在入口内 lazy import,不污染 agent 运行时对 knowledge_base 的轻量 import)。依赖 FastAPI/uvicorn + `tenant_router` + `identity` + `knowledge_base` public。
- **public API surface**:新增 `fleetent kb serve` 入口 + wire 协议 server 端;无对现有 API 的破坏。
- **owned tables**:无(只读 `kb/`)。
- **config namespace**:服务级 `tenant_id`、监听地址、service key 引用(`env:`/`file://`)、默认 `mode`。
- **cross-module 依赖**:**保持 `knowledge_base` ✗→ `platform`**(服务只用 tenant_router/identity/knowledge_base,不 import platform);跑 module-boundaries 护栏确认。
- **数据位置**:服务读本地 `tenants/<t>/kb/`,假定与现有 ingest **同主机**(读服务先行,不要求 ingest 已搬);真正 KB↔平台分机由 ②b 解决。
- **测试**:integration(服务对请求返回 chunks、principal/tenant 校验、鉴权);e2e(agent 经 Slice ① HttpKnowledgeProvider → 本服务 → `kb/`,端到端读)。
- **明确不做(②b)**:ingest worker 搬迁、队列归属(自持 vs management.db)、connector secret 跨机、compose 全栈部署。
