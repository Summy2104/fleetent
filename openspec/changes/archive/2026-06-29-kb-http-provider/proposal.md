## Why

provider 缝已硬化(`harden-kb-provider-seam`):`long_term_ctx` 有默认 `LocalKnowledgeProvider`、可经 `set_knowledge_provider` 注入替换。但**没有 HTTP client 实现**——agent 还无法指向一个远程/外部的 KB 检索端点。这是"KB 独立部署(多 node)"与"换外部 KB(BYO)"两条路共同缺的那块 client。本 change 加 `HttpKnowledgeProvider` + 一份中立 wire 协议 + 配置驱动的注入,**默认行为不变**(未配置 = 仍走 LocalKnowledgeProvider)。这是 Slice ①,纯加法、读侧;KB 服务本体(server)是后续 Slice ②。

## What Changes

- **中立 wire 协议**:定义 KB 检索的 HTTP 契约——请求 `{principal:{user_id,tenant_id}, query, kb_ids, limit}`,响应 `{chunks: [KnowledgeChunk JSON]}`。自家 KB 服务与外部系统都实现这份协议(dogfood:自家不是特权路径)。
- **`HttpKnowledgeProvider`**:实现 `KnowledgeProvider` 契约的 HTTP client——httpx 调配置的 endpoint,带 Bearer service key + `X-Fleetent-Principal` header(复用 `identity.encode_ingress_principal`),把响应反序列化为 `list[KnowledgeChunk]`;HTTP 错误/超时**降级为空**(与现有 `_retrieve_with_timeout(empty=[])` 一致,不中断对话)。
- **agent 侧 provider 选择配置**:`agent.knowledge.provider`(默认 `local`;`http` 含 `url` + 鉴权引用)。未配置或 `local` → 默认 LocalKnowledgeProvider;`http` → 注入 HttpKnowledgeProvider 指向该 url。
- **注入接线**:agent 进程 boot(`agent_app`,现已 `set_database`/`set_vector_backend` 处)按 `agent.knowledge.provider` 决定是否 `set_knowledge_provider(HttpKnowledgeProvider(...))`。

不改变:默认(未配置)检索行为 = LocalKnowledgeProvider 逐字不变;KnowledgeProvider 契约(Slice 1 已定);knowledge_base 检索核;single-machine 不需要任何 HTTP。

## Capabilities

### New Capabilities
<!-- 无 -->

### Modified Capabilities
- `long-term-ctx`: "Optional knowledge provider" 新增 `HttpKnowledgeProvider` 作为可选 built-in provider 实现 + 中立 wire 协议契约 + HTTP 失败降级。
- `agent-knowledge-config`: 新增 `knowledge.provider` 选择(`local` 默认 / `http` 指向 KB 服务 url),决定运行时用 Local 还是 Http provider。

## Impact

- **owning packages**:`fleetent.long_term_ctx`(HttpKnowledgeProvider + 协议)+ `fleetent.agent_config`(`knowledge.provider` 字段)+ `runtime.agent_app`(按配置注入)。
- **public API surface**:`AgentKnowledge` 新增可选 `provider`;新增 `HttpKnowledgeProvider`;`set_knowledge_provider` 不变。
- **owned tables**:无。
- **config namespace**:`knowledge.provider`(agent.yaml);鉴权引用复用既有 secret 引用约定(`env:`/`file://`)。
- **cross-module 依赖**:保持 `long_term_ctx` ✗→ `platform`(HttpKnowledgeProvider 只用 httpx + `identity` + `KnowledgeChunk`,不 import platform);注入由 agent_app 按 agent 自身配置完成(node materialize 该配置进 agent.yaml)。
- **行为**:默认零回归;只有显式配 `http` 的 agent 才走远程。
- **明确不做(Slice ②)**:KB 服务 server 本体、ingest worker/队列/secret 归属、per-tenant 服务部署。本 change 可对 fake HTTP server 测,不依赖真服务存在。
- **测试**:unit(provider 默认 local / 配置解析)+ integration(HttpKnowledgeProvider 对 fake server 返回 chunks、错误/超时降级空、principal/header 正确)。
