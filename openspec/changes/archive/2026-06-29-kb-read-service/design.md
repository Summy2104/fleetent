## Context

Slice ①(`kb-http-provider`)定义了 wire 协议 + client(HttpKnowledgeProvider)。本 change 建 server 端。探子(a8d5f6c4)+ 现场核实结论:
- 读路径注入范式现成 = worker 的 `_use_kb_runtime(tenant)`:`tenant_scope(t)` → `kb_runtime.set_database`/`set_vector_backend` → 调 → 还原。
- **结 2 轻**:`search(query, store, tenant_id, kb_ids, limit, mode, rerank, audit_context)` 的 `mode`/`rerank` 是**显式参数**;读路径里 `active_agent_or_default()` 只被读边角(`retrieval_audit` 开关 search.py:109/graph_search.py:245;`_rerank_settings` rerank 配置 runtime.py:377),核心 mode 不依赖它。
- 鉴权现成 = `identity` 的 `X-Fleetent-Principal` + Bearer(参 `agent_transport.py`)。
- 入口范式 = `worker.py` 的 `main()`+argparse(`fleetent kb-worker`)。
- 租户形态已定 **A(每租户一进程)**。

## Goals / Non-Goals

**Goals:**
- 实现 wire 协议的 per-tenant HTTP 读服务,经 knowledge_base public API 检索,Bearer+Principal 鉴权。
- 端到端:agent(Slice ① http provider)→ 本服务 → `kb/`。

**Non-Goals:**
- 不搬 ingest worker / 队列 / connector secret(②b)。
- 不改 knowledge_base 检索核、不动现有 ingest、不改单机嵌入式路径。
- 不做去全局状态重构(per-tenant 进程使其无必要)。
- 不做 compose 全栈部署接线(②b / 部署 change)。

## Decisions

### 决策:per-tenant 进程,boot 绑定租户、set_database 一次
- 服务启动带 `tenant_id`;boot 时 `tenant_scope(t)` 注入一次。并发请求都同一租户 → 全局 `_kb_db` 被设成同一值,**无 race**。这正是选项 A 的红利:**不碰全局状态、零重构**。
- 请求里 `principal.tenant_id` 必须 == 服务租户,否则拒绝(防串租户)。

### 决策:显式 mode 调 search,边角走默认
- 服务以显式 `mode`(服务级默认 `hybrid`)+ 请求 `kb_ids`/`limit` 调 `knowledge_base.search`。边角 `active_agent_or_default()` 读(retrieval_audit / rerank 配置)在服务进程返回中性默认 —— 可接受;rerank/graph 若启用,由服务级配置驱动(后续按需,本 change 默认 hybrid)。

### 决策:入口模块 + FastAPI 隔离,保护 knowledge_base 轻 import
- 新增 `knowledge_base/serve.py`(或独立入口模块):FastAPI/uvicorn 在入口内 import,**不进 knowledge_base 顶层 import 链**(agent 运行时 import knowledge_base 不应被迫拉 FastAPI)。`fleetent kb-serve --tenant <t> --host --port` 照 worker 范式。

### 决策:保持 knowledge_base ✗→ platform
- 服务只依赖 `tenant_router`(根)、`identity`(根)、`knowledge_base` public、FastAPI。不 import platform。module-boundaries 护栏覆盖。

### 决策:数据同主机假定
- 服务读本地 `tenants/<t>/kb/`,假定现有 ingest 写的就是同一主机的 `kb/`(读服务先行,可与平台/ingest 同机)。真正分机(ingest 也搬走)= ②b。

## Risks / Trade-offs

- **[协议与 Slice ① 漂移]** server/client 两端协议要一致。**Mitigation**:协议已写死在 Slice ① spec;本 change server 实现同一份;e2e 测试用真 HttpKnowledgeProvider 打本服务,撞一致性。
- **[边角默认不合预期]** 服务进程 active_agent 默认导致 rerank/audit 配置非预期。**Mitigation**:本 change 默认 hybrid、不开 rerank;audit 默认关无害;rerank/graph 作为服务级配置后续按需,不在本 change 强求。
- **[与 Slice ① 的执行时序]** 两端代码不重叠(① client / ②a server),可并行;e2e 联调放在后落地的一侧。**Mitigation**:②a 自身用 fake principal/请求测;端到端 agent→service 测在 ① 也落地后补(或本 change 内对 in-process 起服务做 e2e)。

## Migration Plan

- 纯新增服务模块 + 入口,无 schema、不动现有路径。部署:要远程读的部署起 `fleetent kb-serve`,agent 配 `knowledge.provider=http`(Slice ①)指向它;不起则一切照旧(单机嵌入式)。回滚:删服务/还原代码,现有路径不受影响。

## Open Questions

- 服务级 policy(mode/rerank/graph)是否需要更细配置(per-KB):本 change 先服务级默认 hybrid;细化按需,不阻塞。
- e2e 联调归属(本 change 内 in-process 起服务 vs 等 ① 落地后单独 e2e change):实现时按 ① 落地进度定。
