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
- **THEN** 它 import 并调用 `fleetent.intelligence.memory` 的 public API，而不是 import memory store internal

#### Scenario: internal 实现可局部调整
- **WHEN** 某模块重组 internal parser、store、worker 或 adapter 文件
- **THEN** 使用 public API 的调用方不需要修改 import 路径即可继续工作

### Requirement: Module-owned data
每张持久化表 SHALL 有且只有一个 owner module。owner module SHALL 定义该表的 migration、store 访问和
public DTO。其他模块 MUST NOT 直接 query 或 mutate 另一个模块 owned table。

IM 相关表 `im_users`、`im_connectors` SHALL 由统一 IM 模块
（`platform/im_gateway_management`）作为唯一 owner module 拥有。该模块同时承载 IM 身份
映射与 connector 凭证，二者刻意置于同一 IM 模块边界内；旧的 `im_user_store` 与各
`im_connector_*` import 路径 SHALL 仅作为 compatibility shim 保留。

#### Scenario: 模块访问其他模块数据
- **WHEN** reflection 需要分析 memory 质量
- **THEN** 它通过 memory 模块 public API 读写 memory 数据，而不是直接对 `memory_items` 发 SQL

#### Scenario: 新表声明 owner
- **WHEN** 一个 OpenSpec change 新增持久化表
- **THEN** 该 change 在 implementation 开始前标明 owning module

#### Scenario: IM 表归属统一 IM 模块
- **WHEN** 任意模块需要读写 `im_users` 或 `im_connectors`
- **THEN** 它通过统一 IM 模块的 public API 访问，而不是直接对这些表发 SQL，也不 import IM 内部实现文件

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

#### Scenario: cleanup 后 legacy import 可移除
- **WHEN** 已迁移 package 的 first-party imports 都切换到 canonical path
- **THEN** 后续 cleanup spec 可以删除对应 legacy shim

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
系统 SHALL expose the admin CLI through `platform.admin_cli` canonical package paths only; the legacy
`fleetent.admin` shim SHALL NOT remain importable. The admin CLI SHALL be invoked exclusively via the
`fleetent admin` subcommand of the single `fleetent` entrypoint; the standalone `fleetent-admin` console
script SHALL NOT exist in `pyproject.toml` (its deprecation shim is removed). `platform.admin_cli.main.main`
SHALL remain importable as the canonical implementation that `fleetent admin` delegates to.

#### Scenario: New admin CLI package entrypoint exists
- **WHEN** 调用方导入 `fleetent.platform.admin_cli.main.main`
- **THEN** 导入成功

#### Scenario: Legacy admin entrypoint is removed
- **WHEN** 调用方导入 `fleetent.admin`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: No standalone admin console script
- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-admin` 入口；admin CLI 仅经 `fleetent admin` 子命令暴露

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
系统 SHALL expose governance implementation through `fleetent.governance` canonical package paths only;
legacy top-level governance shim modules SHALL NOT remain importable.

#### Scenario: Governance package exists
- **WHEN** 调用方导入 `fleetent.governance`
- **THEN** 导入成功

#### Scenario: Governance canonical modules exist
- **WHEN** 调用方导入 `fleetent.governance.permission_gate`、`fleetent.governance.quota`、`fleetent.governance.audit_log`、`fleetent.governance.blocklist` 或 `fleetent.governance.agent_policy`
- **THEN** 导入成功

#### Scenario: Legacy governance imports are removed
- **WHEN** 调用方导入 `fleetent.permission_gate`、`fleetent.quota`、`fleetent.audit_log`、`fleetent.blocklist` 或 `fleetent.agent_policy`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Governance owns existing governance data responsibilities
- **WHEN** quota、audit log 或 blocklist 访问既有持久化数据
- **THEN** 该访问由 `fleetent.governance` package 内的实现负责
- **AND** 本 change 不新增数据库 schema

#### Scenario: Platform and channels use governance public API
- **WHEN** platform 或 channels 模块需要 audit log、blocklist、quota 或 permission gate 能力
- **THEN** 它们通过 `fleetent.governance` canonical public API 调用
- **AND** legacy 顶层 shim 不存在

#### Scenario: Runtime uses governance through public API
- **WHEN** agent runtime 需要权限审批或工具访问策略
- **THEN** 它通过 `fleetent.governance` public API 调用治理能力
- **AND** governance package 不反向 import runtime entrypoint

### Requirement: Source module organization map
系统 SHALL 在架构文档中维护 `src/fleetent` 的模块组织映射（现模块 → 目标归属：核 / ①边缘 / ②控制 / ③编排 / ④摄取 / 共享基座）。模块边界本身由依赖护栏测试强制（见本 spec 其它 requirement）；legacy 平铺模块向 package 的迁移已完成，原 `source-module-organization-roadmap.md` 已退场（其模块归属内容并入下述架构文档）。

#### Scenario: 模块归属映射存在
- **WHEN** 读者查看架构文档
- **THEN** `docs/architecture/target-architecture.md` §10「现模块 → 目标归属（速查）」给出各模块（runtime/platform/governance/channels/intelligence 各域、integrations、observability、infrastructure）的目标归属

### Requirement: Integrations package migration
系统 SHALL expose external capability integrations through `fleetent.integrations` canonical package paths
only; legacy top-level integrations shim modules SHALL NOT remain importable.

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

#### Scenario: Legacy MCP import is removed
- **WHEN** 调用方导入 `fleetent.mcp_client`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy sandbox import is removed
- **WHEN** 调用方导入 `fleetent.sandbox_client`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Runtime and server use integrations through public API
- **WHEN** server 注册 MCP servers 或 tools 创建 sandbox client
- **THEN** 它们通过 `fleetent.integrations` public API 调用外部能力接入
- **AND** integrations package 不反向 import agent runtime entrypoint

### Requirement: Memory layer package migration
系统 SHALL expose User Memory implementation through `fleetent.intelligence.memory` canonical package paths
only; the legacy `fleetent.memory_layer` shim SHALL NOT remain importable.

#### Scenario: Memory canonical package exists
- **WHEN** 调用方导入 `fleetent.intelligence.memory`
- **THEN** 导入成功

#### Scenario: Memory canonical package exports public API
- **WHEN** 调用方从 `fleetent.intelligence.memory` 导入 `MemoryItem`、`MemoryType`、`extract_and_update`、`search`、public operations 或 `run_memory_maintenance`
- **THEN** 导入成功
- **AND** public object 行为与迁移前保持一致

#### Scenario: Legacy memory import is removed
- **WHEN** 调用方导入 `fleetent.memory_layer`
- **THEN** 导入失败并显示该 legacy module 不再存在

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

### Requirement: Flat-path package migration cleanup
flat→package 迁移收尾后，系统 SHALL expose runtime、model、tools、skills、session 五个能力域的实现 through 各自 canonical package paths only；这些域对应的 legacy 顶层平铺 shim 模块 SHALL NOT remain importable。

#### Scenario: Runtime canonical package exists
- **WHEN** 调用方导入 `fleetent.runtime` 或 `fleetent.runtime.loop`
- **THEN** 导入成功

#### Scenario: Model canonical package exists
- **WHEN** 调用方导入 `fleetent.model` 或 `fleetent.model.router`
- **THEN** 导入成功

#### Scenario: Tools canonical package exists
- **WHEN** 调用方导入 `fleetent.tools` 或 `fleetent.tools.registry`
- **THEN** 导入成功

#### Scenario: Skills canonical package exists
- **WHEN** 调用方导入 `fleetent.skills` 或 `fleetent.skills.registry`
- **THEN** 导入成功

#### Scenario: Session canonical package exists
- **WHEN** 调用方导入 `fleetent.session` 或 `fleetent.session.manager`
- **THEN** 导入成功

#### Scenario: Legacy runtime imports are removed
- **WHEN** 调用方导入 `fleetent.agent_loop`、`fleetent.context_mgr`、`fleetent.agent_runtime`、`fleetent.sub_agent`、`fleetent.sub_agent_lifecycle`、`fleetent.termination`、`fleetent.loop_detector`、`fleetent.budget`、`fleetent.cancellation`、`fleetent.message_hygiene`、`fleetent.error_classifier` 或 `fleetent.tool_guardrails`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy model imports are removed
- **WHEN** 调用方导入 `fleetent.model_router` 或 `fleetent.provider_health`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy tools imports are removed
- **WHEN** 调用方导入 `fleetent.tool_registry`、`fleetent.tool_result_truncation`、`fleetent.plugin_loader`、`fleetent.vision_client`、`fleetent.image_gen_client` 或 `fleetent.multimodal`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy skills imports are removed
- **WHEN** 调用方导入 `fleetent.skill_registry` 或 `fleetent.skill_audit`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy session imports are removed
- **WHEN** 调用方导入 `fleetent.session_mgr` 或 `fleetent.session_index`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Legacy sandbox flat-path modules are removed
- **WHEN** 调用方导入 `fleetent.sandbox_config`、`fleetent.sandbox_manager`、`fleetent.sandbox_enablement`、`fleetent.sandbox_cleanup`、`fleetent.sandbox_secrets` 或 `fleetent.sandbox_output_truncation`
- **THEN** 导入失败并显示该 legacy module 不再存在

#### Scenario: Cleanup is behavior-preserving
- **WHEN** flat-path cleanup change 完成
- **THEN** 全量测试（`ANTHROPIC_API_KEY=sk-test-dummy uv run pytest -q`）通过，且仓库不包含运行时代码或数据库 schema 变更

### Requirement: Capability docs use canonical package names
系统 SHALL 在当前架构文档和 capability docs 中使用已迁移模块的 canonical package 名称，而不是把已删除 legacy path 描述为主要实现位置或可用 public API。

#### Scenario: Current docs reference canonical memory package
- **WHEN** 读者查看当前 memory、long-term context、reflection 或 vector-store capability docs
- **THEN** 文档使用 `fleetent.intelligence.memory` 或 `intelligence.memory` 表示 User Memory public API

#### Scenario: Current docs reference canonical integrations packages
- **WHEN** 读者查看当前 MCP、sandbox、connectors 或 architecture docs
- **THEN** 文档使用 `fleetent.integrations.mcp` 和 `fleetent.integrations.sandbox` 表示外部能力接入实现

#### Scenario: Current docs reference canonical governance package
- **WHEN** 读者查看当前 governance、tools、IM gateway 或 platform capability docs
- **THEN** 文档使用 `fleetent.governance` 下的 public API 表示权限、审批、quota、audit 和 blocklist 能力

#### Scenario: Current docs reference canonical admin CLI entrypoint
- **WHEN** 读者查看当前 platform 或 architecture docs
- **THEN** 文档使用 `fleetent.platform.admin_cli` 或 `fleetent admin` 子命令表示 admin CLI 入口
- **AND** 不把 `fleetent.admin` 或已移除的 `fleetent-admin` console script 描述为当前实现入口

#### Scenario: Deleted legacy paths are not described as current APIs
- **WHEN** 当前 docs 描述 memory、governance、integrations 或 admin CLI
- **THEN** 文档不把已删除 legacy import path 描述为仍可用 public API

#### Scenario: Historical archive docs remain historical
- **WHEN** 搜索 `docs/archive/**` 或 `openspec/changes/archive/**`
- **THEN** 历史记录可以保留 legacy 模块名
- **AND** 本 change 不要求重写历史设计记录

### Requirement: Agent runtime 不依赖 platform
agent-runtime 模块（`runtime`、`session`、`im_gateway`、`intelligence`、`tools`、`integrations`、`model`、`observability`、`governance`）MUST NOT `import fleetent.platform`。需要协调 platform stores（API 密钥、IM 账号、用户管理等）的编排逻辑 SHALL 落在 platform 层；agent-runtime 模块仅暴露被 platform 调用的 public API 或共享可读存储。

#### Scenario: governance 不 import platform
- **WHEN** 检查 `fleetent.governance` 下任一模块的 import
- **THEN** 不存在对 `fleetent.platform` 的 import

#### Scenario: 级联编排归 platform
- **WHEN** 封禁用户需要吊销其 API 密钥并禁用其 IM 账号（均为 platform-owned 数据）
- **THEN** 该级联编排由 platform 层模块执行，而不是由 governance 模块 import platform store 来执行

### Requirement: Admin CLI 直写管理库的边界

`fleetent admin` CLI 直接访问管理面 store（不经平台 HTTP server 写管理库）SHALL 仅限以下三类：

- **真 bootstrap**：必须在 server 起来之前/之外运行的操作（如 `seed-builtin-admin` 创建首个内置 admin、`init-config`、`validate-config`）。
- **基础设施供给**：`agent-node-registry` spec 已界定为"先于/独立于平台业务管理"的 ops 入口（node 登记/列举/注销/pin/unpin）。
- **危险宿主级维护**：在平台宿主上人工执行的低频危险操作（`diagnostics`、`maintenance`）。

业务控制面操作——租户/团队创建、用户归属（`tenant_id`）设置、审批人（`approver_user_id`）配置及同类——MUST 经平台 HTTP API 执行，MUST NOT 提供绕过 server（直写管理库、跳过 session 鉴权与 HTTP 审计）的 CLI 路径。判据是"该操作是否必须在 server 之前/之外运行"，而非"是否已有 HTTP 等价"。

#### Scenario: 业务控制面操作无直写 CLI

- **WHEN** 查看 `fleetent admin` 子命令集合
- **THEN** 不存在 `create-tenant` / `list-tenants` / `create-team` / `set-user-tenant` / `set-approver` 等直写管理库的租户管理命令
- **AND** 这些操作仅经 `/admin/tenancy/*` HTTP API 提供

#### Scenario: bootstrap 与基础设施供给可直写

- **WHEN** 运维执行 `fleetent admin seed-builtin-admin` 或 `fleetent admin node register`
- **THEN** 允许直接写管理库——前者是 server 起来前的 bootstrap，后者是 spec 认可的基础设施供给入口

#### Scenario: 新增业务控制面操作走 HTTP

- **WHEN** 后续新增任一业务控制面写操作（管理库业务实体的增删改）
- **THEN** 它经平台 HTTP API 暴露，而不是新增直写管理库的 admin CLI 命令

