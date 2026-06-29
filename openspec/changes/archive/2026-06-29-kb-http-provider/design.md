## Context

`harden-kb-provider-seam` 已落地:`long_term_ctx` 有 `KnowledgeProvider` 硬契约 `(Principal, query, kb_ids, limit, audit)→list[KnowledgeChunk]`、默认 `LocalKnowledgeProvider`、`set_knowledge_provider` 注入口;`_search_knowledge` 解析 scope 后调当前 provider,失败由 `_retrieve_with_timeout(empty=[])` 降级。注入点现成:`agent_app._init_agent_db_schema`(agent 进程 boot,347-348 已 `kb_runtime.set_database`/`set_vector_backend`)。鉴权范式现成:`identity.encode_ingress_principal` + `X-Fleetent-Principal` header(`INGRESS_PRINCIPAL_HEADER`)+ Bearer service key(参 `agent_transport.py`)。`knowledge-service-config` spec 明确 standalone KB 服务 config 留给后续 change——本 change 只做 agent 侧"指向远程 KB"的 client,不做 server(Slice ②)。

## Goals / Non-Goals

**Goals:**
- 中立 wire 协议 + `HttpKnowledgeProvider`(httpx client,鉴权,反序列化,失败降级)。
- `agent.knowledge.provider`(local 默认 / http)+ agent_app 按配置注入。
- 默认零回归;可对 fake server 测,不依赖真服务。

**Non-Goals:**
- 不做 KB 服务 server、ingest 归属、per-tenant 服务部署(Slice ②)。
- 不改 KnowledgeProvider 契约、knowledge_base 检索核、LocalKnowledgeProvider 行为。
- 不在协议里塞 policy(各 provider 自管;远程端点自带 ranking)。

## Decisions

### 决策:wire 协议 = 契约的 JSON 化,单一检索端点
- 请求 `POST {url}` body `{"principal":{"user_id","tenant_id"}, "query", "kb_ids":[...], "limit"}`;响应 `{"chunks":[KnowledgeChunk JSON]}`。
- **一个检索端点**(非分 search/graph):契约就是"scope+query→chunks",远程端点内部决定 hybrid/graph,client 不关心。与 Slice 1"policy 不进契约"一致。
- KnowledgeChunk JSON 形状取其 dataclass 字段(id/document_id/tenant_id/kb_id/filename/content/position/score/source/source_url/metadata)。

### 决策:HttpKnowledgeProvider 落 long_term_ctx,保护解耦
- 与 `LocalKnowledgeProvider` 同处 `long_term_ctx`;只依赖 httpx + `identity`(根)+ `KnowledgeChunk`(knowledge_base public),**不 import platform**,护栏不破。
- 失败:HTTP 非 2xx / 超时 / 网络错 → 记日志返回 `[]`。外层 `_retrieve_with_timeout` 已兜超时;client 内部再兜 HTTP 错(确保异常不冒泡)。

### 决策:配置在 agent.knowledge.provider,agent_app 按配置选 provider
- `AgentKnowledge` 加可选 `provider`:`{type: "local"|"http", url?, auth_ref?}`,默认 local。
- agent_app boot:若 `provider.type=="http"`,`set_knowledge_provider(HttpKnowledgeProvider(url, service_key=resolve(auth_ref)))`;否则不注入(留默认 Local)。
- **这就是"node 在 agent 进程注入"的落地**:node materialize agent.yaml 时写入 provider 配置,agent 进程 boot 据此注入。本 change 让 agent_config 支持该字段 + agent_app 据此注入;node materialize 写该字段是平凡补充(随用随加,默认 local 不影响存量)。

### 决策:service key 复用既有 secret 引用约定
- `auth_ref` 用 `env:NAME` / `file://PATH`(与 connector credential_ref 同约定),运行时解析为 Bearer token。无新 secret 机制。

## Risks / Trade-offs

- **[协议定型过早]** Slice ② server 还没建,协议可能要调。**Mitigation**:协议就是已落地契约的直接 JSON 化(scope+query→chunks),面很窄;Slice ② server 实现同一份,两端 fleetent 自己写、对着改成本低。
- **[失败语义双重兜底]** timeout 框架 + client 内 try/except 可能重复。**Mitigation**:明确分工——client 兜 HTTP/网络错返回空;外层兜整体超时;都导向空,无害。
- **[默认行为回归]** provider 选择逻辑误改默认。**Mitigation**:默认 local 零注入路径与现状逐字一致;测试断言未配置时仍走 LocalKnowledgeProvider。

## Migration Plan

- 纯加法 + 配置字段。默认 local → 存量 agent 零变化。部署即生效;要远程的 agent 显式配 `provider.type=http`。回滚还原代码。

## Open Questions

- 协议是否需要分页 / rerank 提示:暂不;契约保持 scope+query→chunks,远程端点自管。Slice ② 实现时若需再扩。
