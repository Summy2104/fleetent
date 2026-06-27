# agent-versioning

## REMOVED Requirements

### Requirement: agent_versions table schema
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;配置版本化为半成品(激活旧版本只回滚部分字段、误导)。本次确立 `agents` 表为 agent 配置单一当前态真相源,退役该机制。`agent_versions` 表整体退役。
**Migration**: 运行时配置字段(`system_prompt`/`allowed_tools`/`skills_dir`/`model_overrides`/`memory_namespace`)改由 `agents` 表当前态直接承载(见新 capability `agent-config-single-source`);`mcp_server_ids` 收敛到 `agent_mcp_servers` 关系表为唯一真相源(见 `agent-mcp-binding`);`template_id` 全仓零读、前端零显示,确属死列,随表丢弃不迁移;`agent_versions` 表、`(agent_id, version)` 唯一约束、`version` 列整体移除,无快照表替代。

### Requirement: Active version pointer is single source of truth
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;配置版本化为半成品(激活旧版本只回滚部分字段、误导)。本次确立 `agents` 表为 agent 配置单一当前态真相源,退役该机制。`active_version_id` 间接寻址不再需要。
**Migration**: agent 配置直接读 `agents` 表当前态(见 `agent-config-single-source`);`agents.active_version_id` 列与"激活版本=切指针"语义整体退役,无替代指针。

### Requirement: Versions are immutable
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;配置版本化为半成品(激活旧版本只回滚部分字段、误导)。本次确立 `agents` 表为 agent 配置单一当前态真相源,退役该机制。不再保留历史版本快照,故"版本不可变"无对象可约束。
**Migration**: 编辑 agent 配置改为对 `agents` 表当前态原地 `UPDATE`(见 `agent-config-single-source`);不再产生新版本行,无历史快照不可变性需要维护。

### Requirement: Session locks to its initial snapshot
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;配置版本化为半成品(激活旧版本只回滚部分字段、误导)。本次确立 `agents` 表为 agent 配置单一当前态真相源,退役该机制。无多版本即无"锁定到初始版本"语义。
**Migration**: 会话配置一致性改由 `agent-config-single-source` 的当前态语义承载;`session` 元数据中的 `agent_version_id` 字段整体退役,无版本指针替代。

### Requirement: Backfill version 1 for pre-existing agents
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;配置版本化为半成品(激活旧版本只回滚部分字段、误导)。本次确立 `agents` 表为 agent 配置单一当前态真相源,退役该机制。`agent_versions` 表移除后无需向其回填。
**Migration**: 迁移把现存版本行的当前态字段折叠回 `agents` 表后丢弃 `agent_versions`(见 `agent-config-single-source` 的迁移计划);回填合成 version 1 的逻辑整体退役,无替代回填。

### Requirement: AgentSnapshot is the runtime representation
**Reason**: snapshot 的 `version`/`version_id` 字段随版本化退役。但"runtime 从存储加载一份 agent 配置供本轮使用"这一行为本身仍活着,且已核实其加载路径是 **file-sourced(来自 agent.yaml、零 DB 访问)**,从不依赖 DB 版本表。故此 requirement 以"版本快照"为框架的表述退役,行为另有承载。
**Migration**: 运行时配置加载继续由 `runtime/snapshot.py` 的 file-sourced 路径承载——从 materialize 出的 `agent.yaml`(自 `agents` 当前态物化)构建快照,零 DB 访问;snapshot 的 `version`/`version_id` 字段移除。运行时配置表示语义见 `agent-config-single-source`。

### Requirement: agent_versions records its originating template
**Reason**: askit/spec-driven 部署器已退役。`template_id`(agent 来自哪个模板的溯源)全仓零读、前端零显示,确属死列。
**Migration**: `template_id` 随 `agent_versions` 表一并丢弃,不迁移到 `agents`;agent 创建仍需既有模板(见 `agent-admin-api` 的"creation requires an existing template"),但"创建后记录来源模板"这一未被消费的溯源退役,无替代。
