# module-boundaries Specification

## Purpose
TBD - created by archiving change define-module-boundaries-and-code-organization. Update Purpose after archive.
## Requirements
### Requirement: 模块化单体 package map
系统 SHALL 为新增和已迁移代码定义规范的模块化单体 package map。规范 top-level package SHALL 包括
`runtime`、`governance`、`platform`、`channels`、`intelligence`、`integrations`、
`observability`、`infrastructure`。

#### Scenario: 新模块遵循 package map
- **WHEN** 新增一个 capability 的实现代码
- **THEN** 该实现代码放入对应 capability 归属的规范 package

#### Scenario: legacy 平铺模块暂时保留
- **WHEN** 现有平铺模块没有被新的 OpenSpec change 大幅修改
- **THEN** 该模块可以暂时保留在原 import 路径

### Requirement: Public API boundary
每个模块 package SHALL 通过文档化的 public API surface 暴露跨模块行为。其他模块 MUST 调用 public API，
并且 MUST NOT import 被 `_internal`、leading underscore 或 capability 文档标记为 internal 的实现文件。

#### Scenario: 跨模块 import 使用 public API
- **WHEN** `long_term_ctx` 需要检索用户记忆
- **THEN** 它 import 并调用 `memory_layer` 的 public API，而不是 import memory store internal

#### Scenario: internal 实现可局部调整
- **WHEN** 某模块重组 internal parser、store、worker 或 adapter 文件
- **THEN** 使用 public API 的调用方不需要修改 import 路径即可继续工作

### Requirement: Module-owned data
每张持久化表 SHALL 有且只有一个 owner module。owner module SHALL 定义该表的 migration、store 访问和
public DTO。其他模块 MUST NOT 直接 query 或 mutate 另一个模块 owned table。

#### Scenario: 模块访问其他模块数据
- **WHEN** reflection 需要分析 memory 质量
- **THEN** 它通过 memory 模块 public API 读写 memory 数据，而不是直接对 `memory_items` 发 SQL

#### Scenario: 新表声明 owner
- **WHEN** 一个 OpenSpec change 新增持久化表
- **THEN** 该 change 在 implementation 开始前标明 owning module

### Requirement: Module-owned configuration namespace
每个模块 SHALL 拥有稳定的配置命名空间。新增配置 SHALL 放在 owning module 的 namespace 下，除非该配置
属于共享 infrastructure。

#### Scenario: 模块新增功能配置
- **WHEN** vector search 新增 backend 选择配置
- **THEN** 该配置放在 `vector_store.*` 或文档化的 vector-store namespace 下

#### Scenario: 共享 infrastructure 配置
- **WHEN** 某配置控制所有 store 使用的 database runtime
- **THEN** 该配置属于 infrastructure 或 deployment 契约，而不是某个功能模块 namespace

### Requirement: Dependency direction
模块依赖 SHALL 遵循现有架构方向：入口层调用 runtime，runtime 调用能力模块，能力模块调用基础设施。低层
模块 MUST NOT import 高层入口或 runtime 模块来触发行为。

#### Scenario: infrastructure 保持独立
- **WHEN** database 或 config infrastructure code 被 import
- **THEN** 它不 import `server`、`agent_loop`、IM adapter 或 feature-specific business logic

#### Scenario: 可拆模块避免反向依赖 runtime
- **WHEN** knowledge-base ingestion 在进程内运行
- **THEN** 它可以被 runtime-facing 模块调用，但不同步 import 或调用 agent runtime internals

### Requirement: Gradual migration with compatibility shim
现有平铺模块 SHALL 渐进迁移。当模块移动到 package 后，旧 import 路径 MAY 保留为 compatibility shim；
shim 只 re-export public names，不包含业务逻辑。

#### Scenario: 迁移期间旧 import 继续可用
- **WHEN** `fleetent.memory_layer` 被迁移到 intelligence package
- **THEN** `fleetent.memory_layer` 可以暂时保留为 re-export public API 的 shim

#### Scenario: shim 不承载业务逻辑
- **WHEN** compatibility shim 存在
- **THEN** 新业务逻辑实现在目标 package 中，而不是写入 shim

### Requirement: OpenSpec changes declare boundary impact
新增或大幅修改代码的 OpenSpec change SHALL 在 implementation 前声明 module owner、public API 变化、owned
tables、config namespace 变化和 cross-module dependencies。

#### Scenario: 新功能 proposal 标明归属
- **WHEN** proposal 新增 capability 实现
- **THEN** 其 design 或 tasks 标明 owning package，以及 public API、table、config namespace 的变化

#### Scenario: 并行工作避免共享契约漂移
- **WHEN** 两个 active changes 都需要修改同一个 public API 或 owned table
- **THEN** 在两个 implementation 窗口继续前，先指定其中一个 change 作为 contract owner

### Requirement: Intelligence capability status documentation
系统 SHALL 保持常乐负责模块的 capability 文档与已归档 OpenSpec changes 和当前实现状态一致。

#### Scenario: Status sections are current
- **WHEN** 读者查看 memory、long-term-ctx、knowledge-base、vector-store、reflection、observability 或 deployment capability 文档
- **THEN** 文档说明当前已完成的 foundation、尚未完成的缺口和下一批候选 specs

#### Scenario: Runtime behavior is unchanged
- **WHEN** 本 change 完成
- **THEN** 仓库不包含运行时代码或数据库 schema 变更

### Requirement: Admin CLI package split
系统 SHALL 将 admin CLI 实现迁入 `platform.admin_cli` package，同时保持现有 `fleetent-admin` 入口兼容。

#### Scenario: New admin CLI package entrypoint exists
- **WHEN** 调用方导入 `fleetent.platform.admin_cli.main.main`
- **THEN** 导入成功

#### Scenario: Legacy admin entrypoint remains compatible
- **WHEN** 调用方导入 `fleetent.admin.main`
- **THEN** 导入成功
- **AND** 行为等价于新的 `fleetent.platform.admin_cli.main.main`

#### Scenario: Console script remains unchanged
- **WHEN** 查看 `pyproject.toml`
- **THEN** `fleetent-admin` 仍指向 `fleetent.admin:main`

#### Scenario: Admin shim does not contain business logic
- **WHEN** 查看 `src/fleetent/admin.py`
- **THEN** 文件只 re-export admin CLI entrypoint
- **AND** 不包含命令业务处理逻辑

### Requirement: Admin CLI command domains
admin CLI SHALL 按命令域拆分实现文件，降低单文件冲突。

#### Scenario: User and IM commands are split
- **WHEN** 查看 `platform.admin_cli`
- **THEN** user commands 和 IM commands 分别位于独立模块

#### Scenario: Pilot operations commands are split
- **WHEN** 查看 `platform.admin_cli`
- **THEN** KB connector、diagnostics 和 observability commands 分别位于独立模块

#### Scenario: Existing admin CLI behavior is preserved
- **WHEN** 运行现有 admin CLI integration tests
- **THEN** 用户、IM、agent/channel、schedule、KB connector、diagnostics 和 observability 命令行为保持不变

#### Scenario: Command modules expose a small registration contract
- **WHEN** 查看 `platform.admin_cli` 的命令域模块
- **THEN** 每个模块通过 `register(subparsers)` 注册自身命令
- **AND** 通过 `handle(args)` 处理自身命令并返回是否已处理

### Requirement: Governance package migration
系统 SHALL 将治理域实现迁入 `fleetent.governance` package，并保持 legacy 顶层 import 路径兼容。

#### Scenario: Governance package exists
- **WHEN** 调用方导入 `fleetent.governance`
- **THEN** 导入成功

#### Scenario: Governance canonical modules exist
- **WHEN** 调用方导入 `fleetent.governance.permission_gate`、`fleetent.governance.quota`、`fleetent.governance.audit_log`、`fleetent.governance.blocklist` 或 `fleetent.governance.agent_policy`
- **THEN** 导入成功

#### Scenario: Legacy governance imports remain compatible
- **WHEN** 调用方导入 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist` 或 `fleetent.agent_policy`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前的 public API

#### Scenario: Governance shims do not contain business logic
- **WHEN** 查看 legacy 顶层 governance 文件
- **THEN** 文件只 re-export `fleetent.governance.*` 的 public names
- **AND** 不访问数据库
- **AND** 不读取配置
- **AND** 不承载业务逻辑

#### Scenario: Governance owns existing governance data responsibilities
- **WHEN** quota、audit log 或 blocklist 访问既有持久化数据
- **THEN** 该访问由 `fleetent.governance` package 内的实现负责
- **AND** 本 change 不新增数据库 schema

#### Scenario: Platform and channels use governance public API
- **WHEN** platform 或 channels 模块需要 audit log、blocklist、quota 或 permission gate 能力
- **THEN** 它们通过 `fleetent.governance` canonical public API 调用
- **AND** legacy 顶层 shim 不承载可被 monkeypatch 的治理状态

#### Scenario: Runtime uses governance through public API
- **WHEN** agent runtime 需要权限审批或工具访问策略
- **THEN** 它通过 `fleetent.governance` public API 调用治理能力
- **AND** governance package 不反向 import runtime entrypoint

### Requirement: Source module organization roadmap
系统 SHALL 维护 `src/fleetent` 的模块组织路线图，用于指导 legacy 平铺模块向模块化单体 package 迁移。

#### Scenario: Roadmap document exists
- **WHEN** 读者查看架构文档
- **THEN** 仓库包含 `docs/architecture/source-module-organization-roadmap.md`

#### Scenario: Roadmap defines target package map
- **WHEN** 读者查看 source module organization roadmap
- **THEN** 文档定义 `runtime`、`platform`、`governance`、`channels`、`intelligence`、`integrations`、
  `observability` 和 `infrastructure` 的目标职责

#### Scenario: Roadmap defines migration order
- **WHEN** maintainer 准备拆分 legacy 平铺模块
- **THEN** roadmap 给出推荐迁移顺序、首批实现型 specs 和不应提前迁移的范围

#### Scenario: Roadmap defines shim policy
- **WHEN** legacy 模块被迁移到 package
- **THEN** roadmap 要求旧 import 路径只保留 re-export shim
- **AND** shim 不承载业务逻辑

#### Scenario: Runtime behavior is unchanged
- **WHEN** source module organization roadmap change 完成
- **THEN** 仓库不包含运行时代码、数据库 schema 或配置行为变更

### Requirement: Integrations package migration
系统 SHALL 将外部能力接入实现迁入 `fleetent.integrations` package，并保持 legacy 顶层 import 路径兼容。

#### Scenario: Integrations package exists
- **WHEN** 调用方导入 `fleetent.integrations`
- **THEN** 导入成功

#### Scenario: MCP canonical package exists
- **WHEN** 调用方导入 `fleetent.integrations.mcp` 或 `fleetent.integrations.mcp.client`
- **THEN** 导入成功
- **AND** canonical path 暴露 MCP client public API

#### Scenario: Sandbox canonical package exists
- **WHEN** 调用方导入 `fleetent.integrations.sandbox` 或 `fleetent.integrations.sandbox.client`
- **THEN** 导入成功
- **AND** canonical path 暴露 sandbox client public API

#### Scenario: Legacy MCP import remains compatible
- **WHEN** 调用方导入 `fleetent.mcp_client`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前 MCP public API
- **AND** 旧路径与 `fleetent.integrations.mcp.client` 共享同一 MCP registry 状态

#### Scenario: Legacy sandbox import remains compatible
- **WHEN** 调用方导入 `fleetent.sandbox_client`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前 sandbox public API
- **AND** 旧路径暴露的 class object 与 `fleetent.integrations.sandbox.client` 相同

#### Scenario: Integrations shims do not contain business logic
- **WHEN** 查看 legacy 顶层 `mcp_client.py` 或 `sandbox_client.py`
- **THEN** 文件只 re-export `fleetent.integrations.*` 的 public names
- **AND** 不创建 MCP session
- **AND** 不创建 Docker subprocess
- **AND** 不承载业务逻辑或 module-level runtime state

#### Scenario: Runtime and server use integrations through public API
- **WHEN** server 注册 MCP servers 或 tools 创建 sandbox client
- **THEN** 它们通过 `fleetent.integrations` public API 调用外部能力接入
- **AND** integrations package 不反向 import agent runtime entrypoint

### Requirement: Memory layer package migration
系统 SHALL 将 User Memory 实现迁入 `fleetent.intelligence.memory` package，并保持 legacy `fleetent.memory_layer` import 路径兼容。

#### Scenario: Memory canonical package exists
- **WHEN** 调用方导入 `fleetent.intelligence.memory`
- **THEN** 导入成功

#### Scenario: Memory canonical package exposes public API
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 memory public API
- **THEN** `MemoryItem`、`MemoryType`、`extract_and_update()`、`search()`、public operations 和 `run_memory_maintenance()` 可用

#### Scenario: Legacy memory import remains compatible
- **WHEN** 调用方导入 `fleetent.memory_layer`
- **THEN** 导入成功
- **AND** 旧路径暴露迁移前的 memory public API

#### Scenario: Memory shim does not contain business logic
- **WHEN** 查看 legacy 顶层 `memory_layer.py`
- **THEN** 文件只 re-export `fleetent.intelligence.memory` 的 public names
- **AND** 不访问数据库
- **AND** 不调用 LLM
- **AND** 不调用 vector store
- **AND** 不承载 memory 业务逻辑

#### Scenario: Memory package owns memory items data access
- **WHEN** memory 功能访问既有 `memory_items` table
- **THEN** 该访问由 `fleetent.intelligence.memory.store` 实现负责
- **AND** 本 change 不新增或修改数据库 schema

#### Scenario: Memory canonical submodules separate responsibilities
- **WHEN** 查看 `fleetent.intelligence.memory` package
- **THEN** 数据模型位于 `models.py`
- **AND** SQLite store 位于 `store.py`
- **AND** LLM extraction 位于 `extraction.py`
- **AND** semantic search 位于 `search.py`
- **AND** public operations 位于 `operations.py`
- **AND** retention / compaction maintenance 位于 `maintenance.py`

#### Scenario: Intelligence modules use memory through public API
- **WHEN** long-term context、reflection 或 vector reindex 需要读取 User Memory
- **THEN** 它们通过 `fleetent.intelligence.memory` public API 调用 memory 能力
- **AND** memory package 不反向 import runtime entrypoint

