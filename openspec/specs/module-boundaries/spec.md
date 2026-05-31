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

