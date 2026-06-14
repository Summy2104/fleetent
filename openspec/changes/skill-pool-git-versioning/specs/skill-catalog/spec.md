## MODIFIED Requirements

### Requirement: catalog 合并治理状态与 skill 级 provenance

`skills` SHALL 合并原 `skill_admin_state` 的治理列（status / global_enabled / audit_verdict / audit_rules / forced / archived_at）与原 `skill_provenance` 的 skill 级列（`source ∈ {managed, adhoc}` / `immutable_fields` JSON）。`current_version` SHALL 被填充为**池 git 中该 skill 子树的最后 commit 标识**（per-skill 版本指针，随池变更更新），不再是未填充占位。

#### Scenario: 治理与 provenance 元数据同表读取
- **WHEN** 平台读取某 skill 的管理元数据
- **THEN** 其 `status` / `global_enabled` / `audit_verdict` / `source` / `immutable_fields` / `current_version` 均从同一 `skills` 行返回

#### Scenario: current_version 反映池 git 版本
- **WHEN** 池中 skill "crm-ops" 被编辑并提交，随后读取其 catalog 行
- **THEN** `current_version` 为该编辑对应的 commit 标识（前移到最新触及该 skill 的 commit）

#### Scenario: current_version 顶替 last_deploy_at
- **WHEN** 检查 `skills` 表结构
- **THEN** 存在 `current_version` 列、不存在 `last_deploy_at` 列
