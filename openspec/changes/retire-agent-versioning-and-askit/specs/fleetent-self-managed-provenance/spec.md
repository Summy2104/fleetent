# fleetent-self-managed-provenance

## REMOVED Requirements

### Requirement: Provenance badge for agents and skills
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`deploy --target fleetent` 已无部署器。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役,故 `spec_owned`/`db_only` 来源区分不再有意义。
**Migration**: 所有 agent/skill 均为控制台手捏的当前态,无 managed/ad-hoc 之分;provenance badge 整体退役,无替代来源标记。

### Requirement: UI edits to managed objects create drift that can flow back
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`override sync`/`promote`/Override Flow 均依赖已死的 askit 回流链路。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役。
**Migration**: UI 编辑即当前态本身,无 spec 基线可 diff、无 drift 概念;drift 标记与 promote-back-to-spec 链路整体退役,无替代回流。

### Requirement: Discarded drift is restored by spec on next deploy
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`deploy --target fleetent` 已无部署器可覆盖 UI 改动。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役。
**Migration**: 无 spec 基线即无"按 spec 还原 drift"语义;discard/restore-on-deploy 链路整体退役,无替代还原。

### Requirement: Immutable fields restored on deploy
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`deploy --target fleetent` 已无部署器可强制还原 immutable 字段。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役。
**Migration**: agent 身份字段不可变性由 agent 身份模型(stable `agent_id`)承载,与 deploy 还原无关;"deploy 时强制还原 spec 值"与对应 UI 警告整体退役,无替代还原路径。

### Requirement: Ad-hoc to managed via decompile keeps identity
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`decompile`(反编译为 spec、入 git)依赖已死的 spec 体系。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役,故无 ad-hoc→managed 提升语义。
**Migration**: 所有 agent 即当前态,无 ad-hoc/managed 之分,无需 decompile 提升;`agent_id` 稳定性由 agent 身份模型继续保证,decompile 链路整体退役,无替代。

### Requirement: Source switch never rebuilds the object
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`deploy --target fleetent` 的 adopt/同名收编依赖已死的部署器。本次确立 `agents` 表为 agent 配置单一当前态真相源,apply 驱动的 managed 收编整体退役,故无 provenance 切换可言。
**Migration**: 不再有 provenance 来源切换;agent 行始终原地存活、`agent_id` 稳定性由 agent 身份模型继续保证;deploy adopt 同名收编语义整体退役,无替代。
