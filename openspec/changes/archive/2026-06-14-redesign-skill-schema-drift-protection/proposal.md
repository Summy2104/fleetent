## Why

Skill 子系统要支撑完整的运行时进化生命周期（公共池 → 绑定 → 隔离部署 → 运行时进化 → 回流 → 保护）。现状已建约 70%（公共管理 / 绑定 / 隔离部署 / 运行时自进化均 live），但缺「部署保护」与「回流」两块。

落地保护之前先暴露出一个数据模型硬伤：`skill_provenance.drift` 以 `skill_name` 为主键，是 **per-skill 全局**一个标志，而 drift 本质是 **per-agent** 的（agent A 改了它那份 skill 副本、agent B 没改）。现有 schema 根本表达不了「A 漂移、B 没漂移」，导致部署保护无法正确实现。

本 change（3 期路线的第 1 期）做地基重设计 + 部署保护止血；池的 git 版本化（第 2 期）与回流审流（第 3 期）不在本次范围。

## What Changes

- **新增 `skills` 主表**（management.db）：池 catalog 的权威元数据源，合并现有 `skill_admin_state`（治理）与 `skill_provenance` 的 per-skill 列（`source`/`immutable_fields`），并新增 `current_version` 池 head 指针。表只存元数据/索引，skill 内容仍在文件系统池，不入库。
- **扩展 `agent_skills`**（绑定 + per-agent 部署态）：新增 `base_version`（该 agent 物化自的池版本，回流基准）、`drift`（这个 agent 副本是否分叉）、`drift_at`。**drift 从 `skill_provenance` 搬到这里，键终于对了**。
- **删除 `skill_provenance` 表**：列已重分配（`source`/`immutable_fields` → `skills`；`drift` → `agent_skills`；死列 `last_deploy_at` 丢弃）。**BREAKING**（管理表结构变更，需数据迁移）。
- **部署保护**：`materialize._copy_skills` 变 drift 感知——重新部署时若某 agent 该 skill 的 `drift=1`，**不覆盖**该副本（保住未回流的运行时进化内容）。现状无条件 `copytree` 覆盖会抹掉进化结果。
- **drift 维护单向 platform**：drift 由 platform 读 agent home 副本产物判定（agent 侧 `write_skill` 已把 `SkillWriteProvenance` 注入 SKILL.md frontmatter；或比对 `base_version` 内容哈希），**绝不由 agent 反写 platform 表**（核心架构契约）。本 change 纯 platform，不动 agent 运行时。
- **移除 inert 调和端点**：`POST /admin/skills/{name}/provenance/{promote,discard}` 与 `askit_override()`（操作即将删除的 `skill_provenance`，均为 no-op 占位）。**BREAKING**（API 端点移除）。真回流调和留待第 3 期用 reflection inbox 重建。
- **去 askit 品牌命名**：`askit_override` 直接删除。

## Capabilities

### New Capabilities
- `skill-catalog`: `skills` 主表作为池 catalog 的权威元数据源（仅元数据/索引、内容在文件系统池），合并治理状态 + skill 级 provenance（source/immutable_fields）+ `current_version` 池版本指针。
- `skill-drift-protection`: 部署期保护——per-agent drift 检测（platform 读 agent home 产物）+ materialize 保留已漂移副本不覆盖 + binding 上记录 `base_version`。

### Modified Capabilities
- `skill-provenance`: drift 重定位到 per-agent 绑定；删除独立 `skill_provenance` 表；skill 级 `source`/`immutable_fields` 迁入 `skill-catalog`；移除 promote/discard 调和端点（回流留待后续 change）。
- `skill-agent-binding`: `agent_skills` 扩展 `base_version`/`drift`/`drift_at`，承载 per-agent 部署态。
- `skill-admin-api`: `list` 响应形变（`source` 改读 `skills` 主表、drift 改为 per-agent 聚合语义）。注：provenance promote/discard 端点的规范本就在 `skill-provenance` 的「Override reflow hooks」需求下，已在该 capability 的 REMOVED 中处理。

> 注：admin console 前端若存在 provenance promote/discard 按钮与 per-skill drift badge，属随端点移除的前端清理，落 tasks；`skill-admin-ui` 规范未承载该 affordance，故不产生 spec delta。

## Impact

- **owning package**: `platform`（`skill_management` + `agent_lifecycle/materialize`）。
- **public API surface**:
  - `skill_admin_store`：移除/重构 provenance 函数（`set_provenance`/`get_provenance`/`mark_drift`/`clear_drift`/`_set_drift`/`is_immutable_change`）——包内私有、无跨包 import，**无需 re-export shim**；`get_state`/`set_*` 改读写新 `skills` 表；`agent_skills` 读写扩展 `base_version`/`drift`/`drift_at`。
  - `skill_admin_api`：移除 2 个 provenance 端点 + `askit_override`；`list_skills`/`edit_skill` 响应形变；`create_skill`/`_import_skill_dir`/`_publish` 的 `source` 管线调整。
  - `materialize._copy_skills`：行为变（drift 感知）+ 写 `base_version`。
- **owned tables**（management.db，Alembic 维护，**迁移号 apply 时再定，不写死**）：新增 `skills`；修改 `agent_skills`（加 `base_version`/`drift`/`drift_at`）；删除 `skill_provenance`。
- **config namespace**: 无新增。
- **cross-module dependencies**: platform 读 agent 侧 home 文件 + `skill_registry` public API（`_resolve_skills_dir`）判 drift——单向 platform→agent 读，不反写。`reflection_management` 的 `SkillProposal` 复用留待第 3 期。
- **migration/shim plan**: 数据迁移 backfill `skills`（从 `skill_admin_state` + `skill_provenance` per-skill 列）；`agent_skills` 加列（default `drift=0`）；迁移 `skill_provenance` 的 `source`/`immutable_fields` 入 `skills` 后删表。无跨包 shim。
- **out of scope**: 池 git 版本化（第 2 期）、回流审流与真调和算子（第 3 期）；`docs/architecture/data-model.md` 与 `openspec/specs/` 主 specs 不在本 change 改动（集成车道统一刷）。
