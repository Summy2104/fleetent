# agent-provenance

## REMOVED Requirements

### Requirement: Managed / adhoc provenance badge
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;`deploy --target fleetent` 已无部署器产出 `managed` agent。本次确立 `agents` 表为 agent 配置单一当前态真相源,managed/adhoc provenance 整体退役。
**Migration**: 所有 agent 均为控制台手捏的当前态(见新 capability `agent-config-single-source`);`agents.provenance` 列与对应 badge 整体退役,无替代来源标记。

### Requirement: Stable identity across provenance changes
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;无 managed/adhoc 之分即无 provenance 切换。本次确立 `agents` 表为 agent 配置单一当前态真相源,managed/adhoc provenance 整体退役。
**Migration**: agent `agent_id` 稳定性由 agent 身份模型(stable `agent_id`)独立保证,与 provenance 无关;"provenance flip 保持 identity"语义随 provenance 列退役,无替代。

### Requirement: Drift flag on managed agents
**Reason**: askit/spec-driven 部署器已退役、agent 全部由控制台手捏;drift 汇总依赖已死的 askit 回流(reconciliation owned by askit)。本次确立 `agents` 表为 agent 配置单一当前态真相源,agent 级 drift 汇总整体退役。
**Migration**: UI 编辑即当前态本身,无 spec 基线可比对、无 drift 概念;`agents.drift` 标记与对应 badge 整体退役,无替代漂移标记。
