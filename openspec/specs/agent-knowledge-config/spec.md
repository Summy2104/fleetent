# agent-knowledge-config Specification

## Purpose
TBD - created by archiving change split-agent-knowledge-config. Update Purpose after archive.
## Requirements
### Requirement: Agent knowledge bindings

`agent.yaml` SHALL define Agent-side knowledge access under `knowledge`, not under
`knowledge_base`. The Agent-side config SHALL contain bindings to KB ids and retrieval policy,
but SHALL NOT contain KB source connector construction details such as Google Drive folders or
Confluence spaces. `knowledge.bindings[]` 是运行时绑定的真相载体(快照),由 platform 从 `agent_kbs`
materialize;运行时 SHALL NOT 由 agent 直接查询 `agent_kbs`(保解耦)。该快照 SHALL 经 reconcile 与
`agent_kbs` 保持同步:bind/unbind 后受影响 agent 的 bindings SHALL 被重新 materialize,并在 agent 的
**下一个 session 边界**生效,不在进行中的对话中途改变 KB 范围。

#### Scenario: Agent binds to one or more KBs
- **WHEN** an Agent config declares `knowledge.enabled: true`
- **THEN** it must declare at least one `knowledge.bindings[]` entry with `tenant_id` and `kb_id`

#### Scenario: Agent has one default KB at most
- **WHEN** multiple `knowledge.bindings[]` entries are declared
- **THEN** at most one entry may have `default: true`

#### Scenario: Old source connector nesting is not accepted
- **WHEN** an Agent config declares `knowledge_base.google_drive.connectors[]` or
  `knowledge_base.confluence.connectors[]`
- **THEN** Agent config loading fails loudly

#### Scenario: Bind change is materialized and takes effect at session boundary
- **WHEN** 管理员在 platform bind 或 unbind 改了某 agent 的 `agent_kbs`
- **THEN** 受影响 agent 的 `knowledge.bindings` 经 reconcile 从 `agent_kbs` 重新 materialize
- **AND** 更新后的 bindings 在该 agent 的下一个 session 边界生效
- **AND** 进行中的对话不改变其 KB 检索范围

#### Scenario: Running agent does not query agent_kbs directly
- **WHEN** agent 运行时确定其可检索 KB 范围
- **THEN** 它读取自身 agent.yaml 的 `knowledge.bindings` 快照
- **AND** 不查询管理库 `agent_kbs`(无 platform DB 环境下仍可运行)

### Requirement: Agent retrieval policy

Agent-side `knowledge.retrieval_policy` SHALL define how the Agent queries bound KBs. It MAY
include retrieval mode, top_k, rerank enablement, model route references for embedding/rerank,
and a planner opt-in (`use_planner`). When `use_planner` is true, the Agent passive retrieval path
SHALL route through `plan_knowledge_search` + `execute_knowledge_search_plan`(规则型:普通 query 走
hybrid、entity/relation-like query 先 graph、不足 hybrid fill),并把返回的 `KnowledgeChunk` 喂入既有
long-term-ctx 预算/选择管线。When `use_planner` is false(默认),retrieval path SHALL keep using
`search(mode=...)` with behavior unchanged.

#### Scenario: Hybrid retrieval policy
- **WHEN** `retrieval_policy.mode` is `hybrid` and `use_planner` is false
- **THEN** the Agent retrieval path uses hybrid KB search over the bound KBs

#### Scenario: Planner opt-in routes through planner
- **WHEN** `retrieval_policy.use_planner` is true
- **THEN** the Agent passive retrieval path calls `plan_knowledge_search` + `execute_knowledge_search_plan`
- **AND** relation-like queries may be escalated to graph evidence, with hybrid fill when insufficient
- **AND** the returned chunks feed the same long-term-ctx budget and selection pipeline

#### Scenario: Planner is off by default
- **WHEN** `retrieval_policy.use_planner` is not set
- **THEN** it defaults to false
- **AND** retrieval behavior is identical to the current `search(mode=...)` path

#### Scenario: Planner falls back safely without graph data
- **WHEN** `use_planner` is true but the bound KBs have no entity/relation graph data
- **THEN** the planner returns hybrid results and no error is raised

#### Scenario: Model routes are referenced by route key
- **WHEN** `retrieval_policy.embedding_route` or `retrieval_policy.rerank_route` is set
- **THEN** the value references a route key from the Agent model policy
- **AND** this spec treats the value as an opaque route-key string until Agent-scoped model routing
  wires model resolution

### Requirement: Agent retrieval is scoped by bindings

Agent KB retrieval SHALL be limited to the KBs declared in `knowledge.bindings[]`.

#### Scenario: Unbound KB is not queried
- **WHEN** an Agent is bound only to `support-kb`
- **THEN** retrieval does not query `billing-kb`

### Requirement: Agent knowledge bindings are single-tenant

一个 agent 的所有 `knowledge.bindings[]` SHALL 共享该 agent 的 `tenant_id`。materialize 与 agent config 加载 SHALL 校验该不变量,违反时 SHALL fail loudly,而非静默只取第一个 binding 的 tenant。

#### Scenario: All bindings share the agent tenant
- **WHEN** materialize 或加载一个 agent 的 knowledge bindings
- **THEN** 每条 binding 的 `tenant_id` 等于该 agent 的 `tenant_id`

#### Scenario: Cross-tenant binding is rejected
- **WHEN** 某 agent 的 bindings 含与 agent `tenant_id` 不一致的条目
- **THEN** 系统 fail loudly,不静默忽略或只取第一个

### Requirement: Agent knowledge provider selection

`agent.knowledge` MAY 声明 `provider` 选择该 agent 的 KB 检索源。当 `provider.type` 为 `http` 时,SHALL 含远程 KB 检索端点 `url` 与服务鉴权引用(service key,沿用 `env:`/`file://` secret 引用约定);此时 agent 运行时 SHALL 经 `HttpKnowledgeProvider` 调该端点检索,而非本地 knowledge-base。

provider 默认按**部署形态**取值:**managed（node 托管）agent 未显式声明 provider 时 SHALL 默认为 `http`**——由 node 注入中心 kb-serve 的 `url` 与共享 service key `auth_ref`(node 从其配置/平台下发获知),因为 managed agent 可与 KB 分机、读不了本地 KB 文件。**standalone(`fleetent agent run`,与 KB 同机)未声明时保持 `local`**(LocalKnowledgeProvider,in-process 读本地),single-machine dev 无需任何 HTTP 配置。无论 local/http,该 agent 检索 SHALL 携带自身 `principal`(tenant),由(多租户)kb-serve 按 `principal.tenant_id` 路由。

#### Scenario: managed agent 默认 http 指向中心 kb-serve
- **WHEN** node 托管拉起的 agent 未显式声明 `knowledge.provider`
- **THEN** 运行时注入 `HttpKnowledgeProvider` 指向 node 提供的中心 kb-serve `url`(带共享 service key auth_ref)
- **AND** 该 agent 的被动 KB 检索经 HTTP 走中心 kb-serve、携自身 principal,本地不再读 knowledge-base

#### Scenario: standalone 默认仍 local
- **WHEN** `fleetent agent run`(dev,与 KB 同机)未声明 `provider`(或 `provider.type=local`)
- **THEN** 使用默认 `LocalKnowledgeProvider` 读本地 knowledge-base,无需任何远程 KB 端点配置

#### Scenario: HTTP provider points agent at a remote KB
- **WHEN** `agent.knowledge.provider.type=http` 且声明了 `url` 与鉴权引用(或 managed 注入)
- **THEN** agent 进程 boot 时注入 `HttpKnowledgeProvider` 指向该 `url`
- **AND** 该 agent 的被动 KB 检索经 HTTP 走该端点,本地不再读 knowledge-base

#### Scenario: Provider config does not carry connector construction
- **WHEN** 声明 `knowledge.provider`
- **THEN** 它只含检索端点 url 与鉴权引用
- **AND** 不含 KB 源 connector 构造细节(Google Drive folder / Confluence space 等仍不在 agent 侧)

