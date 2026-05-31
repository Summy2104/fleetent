## Context

fleetent 当前已经有比较完整的 capability 文档，但实现代码大多平铺在 `src/fleetent/` 下。这个结构在 MVP
阶段有利于快速推进；但随着 user management、IM management、database runtime、memory、knowledge
base、observability、deployment 等工作并行展开，平铺结构会放大 import 随意、表归属不清、配置命名
冲突、跨模块直接读写等问题。

目标架构仍然是单进程、单仓库、on-premises 友好的模块化单体。我们不在这个阶段引入完整 DDD 框架，也
不把业务模块拆成微服务。本设计只定义模块边界和代码组织规则，让后续多个 worktree / Codex 窗口可以
在同一组契约下并行工作。

本设计与 `introduce-database-runtime-boundary` 配合：DB runtime change 负责具体 `database_url`、
`fleetent.db` 和 adapter 形状；本 change 只规定模块如何声明表归属、如何通过 owner public API 访问
数据，以及新 store 不能绕过 DB runtime 边界。

## Goals / Non-Goals

**Goals:**

- 定义 fleetent 的模块化单体组织模型。
- 建立 capability group 到 Python package 的规范映射。
- 定义 public API 与 internal implementation 约定。
- 定义表归属、配置命名空间归属和 migration 责任。
- 定义符合现有分层架构的依赖方向规则。
- 定义从平铺文件到 package 的渐进迁移策略。
- 为后续可能拆分服务的模块保留边界，但现在不增加进程边界。

**Non-Goals:**

- 不一次性移动所有现有平铺模块。
- 不强制引入 aggregate、repository、domain event、application service 等完整 DDD 目录体系。
- 不把 runtime 拆成多个进程或服务。
- 不实现 database runtime、PostgreSQL adapter 或 DB runtime change 已经负责的 store 迁移。
- 不要求每个 capability 文档立刻对应一个 importable package。

## Decisions

### 1. 采用模块化单体，而不是完整 DDD 或微服务

fleetent 应吸收 DDD 中最有价值的边界思想：bounded context、owned data、统一语言、外部系统
anti-corruption adapter。但不要求每个模块都套完整 DDD 文件结构。

备选方案：

- 完整 DDD：概念边界更强，但对 Python Lean Agent 平台过重，容易产生大量薄抽象。
- 立即微服务化：进程隔离更强，但会引入网络失败、部署复杂度、分布式 trace、版本错配，不符合
  on-premises 简化部署目标。

### 2. 目标 package 按平台关注点组织

目标结构：

```text
src/fleetent/
  runtime/          # agent loop、context 压缩、sub-agent 编排
  governance/       # policy、审批、agent 能力边界
  platform/         # user、agent、API key、admin/auth/control plane
  channels/         # IM、webhook、scheduling 入口
  intelligence/     # memory、knowledge base、long-term context、reflection
  integrations/     # MCP、sandbox、外部 connectors
  observability/    # trace、log、usage、diagnostics
  infrastructure/   # config、database runtime、底层 adapter
```

现有平铺模块可以暂时保留。新增模块如果归属明确，应直接写入目标 package。

### 3. Public API 是唯一跨模块 import 面

每个 package 应通过 `__init__.py`、`api.py` 或 capability 文档明确的 public module 暴露跨模块契约。
实现细节可以放在 `_internal/` 或使用 leading underscore 命名。其他模块不得 import internal 文件。

这样可以让模块内部重构保持局部化：parser、store、worker、adapter 怎么拆，不影响外部调用方。

### 4. 数据归属属于模块，而不是谁方便谁读

每张表有一个 owner module。owner 负责 migration、store 函数和 public DTO。其他模块只能通过 owner
public API 读取或修改数据，不能直接 SQL 访问别人的表。

示例：

- `memory_layer` owns `memory_items`。
- `knowledge_base` owns `documents`、`chunks`、`entities`、`relations`。
- `observability` 如果把 trace 从 JSONL 迁到 SQLite，则 owns trace/log 相关表。
- `reflection` owns `skill_proposals`、`kb_reflection_reports`。

具体连接、事务和参数风格由 DB runtime change 定义，本 change 不重复定义。

### 5. 配置命名空间由模块拥有

每个模块拥有稳定配置命名空间。示例：

- `runtime.*`
- `memory.*`
- `knowledge_base.*`
- `long_term_ctx.*`
- `vector_store.*`
- `embedding.*`
- `observability.*`
- `deployment.*`

共享基础设施配置，例如 `database_url`，属于 infrastructure/deployment 契约。功能模块不应随意增加顶层
settings。

### 6. 迁移期间允许 re-export shim

当现有平铺文件移动到 package 后，旧 import 路径可以暂时保留为兼容 shim。shim 只 re-export public
names，不放业务逻辑。后续 change 逐步迁移 import，等使用归零后再删除 shim。

### 7. 未来服务拆分靠端口边界预留，不靠现在拆进程

可能适合未来独立部署的模块，应避免同步反向依赖 `agent_runtime`。候选包括：

- `knowledge_base`
- `observability`
- `connectors`
- `sandbox`
- vector backend
- embedding backend

请求主链路中的 `runtime`、`governance`、`session`、`long_term_ctx` 先保持进程内，除非出现明确的运维或
规模需求。

## Risks / Trade-offs

- **风险：规则只停留在文档** → 增加轻量检查和 OpenSpec checklist，要求新 change 声明 package、表、
  配置、依赖归属。
- **风险：渐进迁移导致平铺和 package 混合存在** → 明确允许过渡期混合，但要求新代码和被大幅触碰的模块
  向目标 package 靠拢。
- **风险：import 规则对 legacy 代码过严** → 规则先约束新模块和已迁移模块；旧平铺模块等触碰时再迁移。
- **风险：和 DB runtime change 重复** → 本 change 只管 ownership 和 import rule；DB runtime API 细节
  由 `introduce-database-runtime-boundary` 管。
- **风险：package 名和 capability 文档漂移** → 使用 canonical snake_case package name；引入或迁移模块时
  同步更新 `docs/architecture.md` / capability 文档。

## Migration Plan

1. 新增 `module-boundaries` spec，并补充 `db-migration` 的表归属规则。
2. 更新架构文档中的目标 package map。
3. 给 OpenSpec change 增加作者自检项：
   - owning package；
   - public API surface；
   - owned tables；
   - config namespace；
   - cross-module dependencies；
   - 如果移动平铺模块，说明 shim / import 迁移计划。
4. 增加轻量结构检查脚本或测试，用于发现已迁移 package 的明显违规 import。
5. 后续 intelligence、observability、deployment change 按这些规则执行。
6. 现有平铺文件在被大幅修改时顺手迁移，不做一次性大搬家。

回滚成本低，因为本 change 不做大规模机械搬迁。如果某个 package 映射不合适，先改 spec，再继续迁移。

## Active Change Coordination

当前仍在执行的 changes 中，以下项可能触碰共享契约：

- `2026-05-30-user-management`：主要触碰 `platform` package 未来归属，涉及 `user_store`、`api_key_store`、
  `auth`、`audit_log`、`quota`、`user_admin_api`、`server.py`。本 change 不改这些实现文件，只补充
  后续 OpenSpec 作者自检规则。
- `2026-05-30-im-gateway-management`：主要触碰 `channels` / `platform` 边界，涉及 IM 用户、channel
  绑定、connector 配置和 admin API。本 change 不重定义 IM 管理接口。
- `2026-05-29-multi-agent-management`：主要触碰 `platform` / `runtime` / `governance` 边界，涉及
  agent definition、agent invocation、resource isolation。本 change 只定义 package ownership 规则。

`introduce-database-runtime-boundary` 已归档。后续如果本 change 需要提到 DB runtime，只引用
`database-runtime` / `db-migration` specs，不重复定义 `fleetent.db` 具体接口。

## Follow-up Change Candidates

本 change 定义组织规则后，intelligence 方向建议拆成以下独立 OpenSpec changes：

- `vector-store-foundation`：建立 `intelligence.vector_store` package、public API、embedding/vector backend
  adapter 边界；先不接 memory / knowledge business flow。
- `observability-trace-contract`：统一 trace 写入和读取 API，决定 JSONL 与 SQLite trace 的阶段性关系，
  为 reflection 提供稳定读取接口。
- `long-term-context-contract`：定义 `long_term_ctx.build_context` 的 DTO、score、source metadata、token
  预算规则；只做契约和轻量编排，不实现完整 knowledge-base ingestion。

## Open Questions

- 第一个迁移示范模块应选 `intelligence.vector_store` 还是 `observability`？
- 在 legacy 平铺模块仍存在时，import 检查应该严格到什么程度？
- re-export shim 是否需要设置明确删除时间，还是等 `rg` 确认没有旧 import 后再删？
