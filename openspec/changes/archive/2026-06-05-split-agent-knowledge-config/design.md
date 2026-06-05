## Context

当前 KB 配置结构来自 legacy `KnowledgeBaseSettings`。config consolidation 后，`Settings`
已瘦身，但这些 KB construction fields 仍作为 `AgentFile.knowledge_base` 的 legacy block
存在：

```yaml
knowledge_base:
  google_drive:
    connectors:
      - connector_id: support-drive
  confluence:
    connectors:
      - connector_id: support-confluence
```

这从 connector implementation 类型出发，适合 KB operation 层展开所有 connector，
但不适合作为 Agent runtime snapshot。Agent 不应该知道 Google Drive folder、Confluence
space、sync schedule 或 chunking 细节。

本 change 将 KB 配置拆成两份契约：

```text
agent.yaml
  -> Agent 使用哪些 KB，以及如何检索

config/knowledge.yaml
  -> KB 如何建设、同步、索引和维护
```

## Goals / Non-Goals

**Goals:**

- Agent config 只表达 KB bindings 和 retrieval policy。
- KB/platform config 表达 KB 全貌、sources、indexing、sync。
- 默认 KB 配置文件路径为 `<FLEETENT_HOME>/config/knowledge.yaml`。
- 未来 KB service 独立部署时，同一契约可 materialize 到
  `<knowledge-service-home>/config/knowledge.yaml`。
- 不保留旧 Agent-side `knowledge_base.google_drive.connectors[]` 兼容。

**Non-Goals:**

- 不在本 change 设计完整 platform.yaml。
- 不重新设计 KB 存储 schema、parser、sync planner 的业务逻辑。
- 不把 KB source 配置复制到每个 Agent home。

## Decisions

### D1 — Agent 使用 `knowledge` 而不是 `knowledge_base`

Agent 侧配置命名为 `knowledge`，避免和平台 KB construction config 混淆。

```yaml
knowledge:
  enabled: true
  bindings:
    - tenant_id: acme-corp
      kb_id: support-kb
      default: true
      permissions:
        search: true

    - tenant_id: acme-corp
      kb_id: billing-kb
      permissions:
        search: true

  retrieval_policy:
    mode: hybrid
    top_k: 10
    rerank: true
    embedding_route: embedding
    rerank_route: rerank
```

Agent 侧回答的问题是：

- 这个 Agent 能访问哪些 KB？
- 默认 KB 是哪个？
- 检索模式是什么？
- 是否 rerank？
- 使用哪些模型 route 做 embedding/rerank？

### D2 — KB service 使用 `config/knowledge.yaml`

KB/platform 侧配置文件默认路径：

```text
<FLEETENT_HOME>/config/knowledge.yaml
```

服务化部署时可 materialize 到：

```text
<knowledge-service-home>/config/knowledge.yaml
```

示例：

```yaml
knowledge_bases:
  - id: support-kb
    tenant_id: acme-corp
    name: Support Knowledge Base

    indexing:
      chunk_size: 1000
      chunk_overlap: 200
      parser_profile: default
      vector_store: default

    sources:
      - id: support-drive
        type: google_drive
        enabled: true
        folder_id: 1abcDEF_support_docs
        recursive: true
        access_token_env: FLEETENT_GOOGLE_DRIVE_ACCESS_TOKEN
        refresh_token_env: FLEETENT_GOOGLE_DRIVE_REFRESH_TOKEN
        client_id_env: FLEETENT_GOOGLE_DRIVE_CLIENT_ID
        client_secret_env: FLEETENT_GOOGLE_DRIVE_CLIENT_SECRET

      - id: support-confluence
        type: confluence
        enabled: true
        base_url: https://acme.atlassian.net/wiki
        username_env: FLEETENT_CONFLUENCE_USERNAME
        scope_type: space
        space_key: SUPPORT
        include_children: true
        api_token_env: FLEETENT_CONFLUENCE_TOKEN

    sync:
      schedule: "*/30 * * * *"
      mode: incremental
```

KB 侧回答的问题是：

- 有哪些 KB？
- 每个 KB 属于哪个 tenant？
- 每个 KB 有哪些 sources？
- 每个 source 如何认证、同步和索引？
- 索引策略是什么？

### D3 — `sources[]` 取代按类型嵌套 `connectors[]`

KB config 使用统一 `sources[]`：

```yaml
sources:
  - id: support-drive
    type: google_drive
  - id: support-confluence
    type: confluence
```

而不是：

```yaml
google_drive:
  connectors: []
confluence:
  connectors: []
```

原因：

- Agent/platform UI 可以统一展示 Knowledge Sources。
- 新增 Notion、SharePoint、S3、Git、local_directory 时不用扩展一层新 namespace。
- `id + type` 与 models 的 `id + protocol/provider` 风格一致。
- 多个 connector 仍然支持，只是表现为多个 source entries。

### D4 — DB authoring 与 file materialization 分离

平台 DB 仍是 authoring source of truth。部署时 materialize 两份文件：

```text
Agent config:
  platform DB -> <agent-home>/agent.yaml

KB config:
  platform DB -> <FLEETENT_HOME>/config/knowledge.yaml
  or
  platform DB -> <knowledge-service-home>/config/knowledge.yaml
```

Agent home 不复制 KB source/index/sync 细节。

### D5 — Agent/KB 通过 binding 关联

Agent `knowledge.bindings[]` 只引用 `tenant_id + kb_id`。KB service config 中
`knowledge_bases[]` 定义这些 KB 的建设细节。

运行时：

- Agent long-term context 按 binding 限定可检索 KB。
- KB search/sync 按 `knowledge.yaml` 管理 KB construction。
- 未绑定 KB 不应被 Agent 检索。

### D6 — 与 Agent-scoped model routing 可并行

本 change 和 `agent-scoped-model-routing` 可以并行推进，但需要明确边界：

- 本 change owns Agent 的 KB binding / retrieval policy 和 KB service construction config。
- `agent-scoped-model-routing` owns `models.targets/routes`、`ModelPolicySnapshot` 和模型
  provider 调用策略。
- `knowledge.retrieval_policy.embedding_route` / `rerank_route` 只是 route-key 引用，schema
  层可以先作为字符串落地；真正按 route key 解析模型 provider 的 runtime wiring 归
  `agent-scoped-model-routing`。
- 两个 change 都会触碰 `AgentFile`、Agent examples、platform materialize 和 snapshots；
  并行实现时需要在这些文件上协调合并顺序，但业务边界不冲突。

推荐实施顺序：

1. 先落本 change 的 schema/materialize：Agent 只保留 KB bindings，KB source 配置进入
   `config/knowledge.yaml`。
2. 并行或随后落 `agent-scoped-model-routing`：让 retrieval policy 的 route-key 引用接入
   `ModelPolicySnapshot`。

## Error Handling

- Agent `knowledge.enabled=true` 但没有 bindings 时，Agent 启动或检索时 fail loud。
- 多个 binding 都标记 `default: true` 时 fail loud。
- Agent binding 引用不存在的 KB 时，平台 materialize 或运行前校验 fail loud。
- `knowledge.yaml` 中 source id 在同一部署内重复时 fail loud。
- source 缺少 type 或类型必填字段时 fail loud。
- secret-like value 出现在非 `*_env` / credential ref 字段时 fail loud。

## Observability / Operations

KB connector status、sync result、dry-run、check 继续以 source id 维度记录，同时包含：

- tenant_id
- kb_id
- source id
- source type
- last status
- last started/finished time
- redacted error summary

Agent retrieval trace 记录：

- agent
- tenant_id
- kb_ids
- retrieval mode
- top_k
- embedding route
- rerank route

## Risks / Trade-offs

- [多一个配置文件] → 换来 Agent config 简化和 KB service 化边界清晰。
- [短期 platform.yaml 仍未定义] → 本 change 不抢先设计 platform.yaml；`knowledge.yaml`
  可未来被 platform.yaml include 或合并为 `knowledge_bases` namespace。
- [旧 Settings 结构迁移成本] → MVP 未上线，不保留 Agent-side 兼容；测试直接迁移到新契约。
- [并行 change 触碰相同文件] → 通过 D6 明确 owner 边界；实现时以 `agent_config` /
  materialize / examples 为协调点。

## Open Questions

无。以下问题已关闭：

- KB source config 不放 Agent home。
- 默认路径为 `<FLEETENT_HOME>/config/knowledge.yaml`。
- Agent 侧使用 `knowledge.bindings[] + retrieval_policy`。
- KB 侧使用 `knowledge_bases[].sources[]`。
- 不在本 change 设计完整 platform.yaml。
- 可与 `agent-scoped-model-routing` 并行；route-key 字段先作为字符串契约。
