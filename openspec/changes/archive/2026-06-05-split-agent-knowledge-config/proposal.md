## Why

`agent.yaml` 当前把 Agent 使用知识库的配置和知识库自身建设配置混在一起：

- Agent 视角只需要知道可访问哪些 KB、默认查哪个 KB、检索策略是什么。
- Knowledge Base / platform 视角需要知道 KB 全貌：数据源、同步、索引、chunking、
  解析、凭据引用、状态和审计。

config consolidation 后，现有 `knowledge_base.google_drive.connectors[]` /
`knowledge_base.confluence.connectors[]` 主要作为 AgentFile 上的 legacy KB construction
block 存在。它更像 KB 平台配置，不适合长期放在 Agent runtime snapshot 里。继续混放会让
单 Agent 配置膨胀，也会阻碍后续 KB/memory 服务化。

## What Changes

- `agent.yaml` 中的知识库配置精简为 Agent 侧 `knowledge`：
  - KB bindings
  - 默认 KB
  - retrieval policy
  - embedding/rerank route 引用
- 新增 platform/KB service 侧配置文件：
  - 默认路径：`<FLEETENT_HOME>/config/knowledge.yaml`
  - 服务化路径：`<knowledge-service-home>/config/knowledge.yaml`
- `knowledge.yaml` 负责 KB 全貌：
  - `knowledge_bases[]`
  - `sources[]`
  - `indexing`
  - `sync`
  - 数据源 credential env refs
- Agent runtime 不再承载 Google Drive / Confluence source 详情。
- 平台 DB 仍可作为 authoring source of truth；部署时分别 materialize Agent snapshot 和
  KB service/platform snapshot。

## Capabilities

### New Capabilities

- `agent-knowledge-config`: Agent-local KB binding and retrieval policy contract.
- `knowledge-service-config`: Platform/KB-service knowledge base construction config contract.

### Modified Capabilities

- `agent-definition`: Agent file no longer owns KB source connector definitions.
- `knowledge-base`: KB source/index/sync configuration moves behind the KB/platform boundary.
- `platform-agent-lifecycle`: Agent materialization writes KB bindings only; KB materialization writes
  `config/knowledge.yaml`.

## Module Boundary Impact

- **owning package**: `intelligence.knowledge_base` owns KB service config parsing and validation;
  `agent_config` owns Agent KB bindings; `platform` owns materialization.
- **public API surface**: Agent snapshot exposes `knowledge` bindings/policy; KB service exposes a
  validated `KnowledgeConfigSnapshot` for indexing/sync.
- **owned tables**: existing KB tables and `agent_kbs` binding remain conceptually valid; schema may
  be reshaped only if needed to author `knowledge.yaml`.
- **config namespace**:
  - Agent: `agent.yaml.knowledge`
  - Platform/KB service: `config/knowledge.yaml`
- **cross-module dependencies**: Agent runtime may depend on KB public search/binding APIs; KB service
  must not depend on Agent runtime internals.
- **migration / shim plan**: no runtime compatibility shim. MVP is not live, so old
  `knowledge_base.google_drive.connectors[]` and `knowledge_base.confluence.connectors[]` are removed
  from Agent config.

## Impact

- **代码**: `agent_config.py`, KB operations/config loading, platform materialize, admin export/deploy,
  examples/templates/tests.
- **配置**: `config/agent/agent.yaml.example` and local `config/agent.yaml` simplified; new
  `config/knowledge.yaml.example` or OpenSpec example introduced.
- **删除**: Agent-side Google Drive / Confluence connector details.
- **分支**: 基于并合回 `main`。
