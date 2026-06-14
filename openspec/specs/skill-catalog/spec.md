# skill-catalog Specification

## Purpose
TBD - created by archiving change redesign-skill-schema-drift-protection. Update Purpose after archive.
## Requirements
### Requirement: `skills` 主表是池 catalog 的权威元数据源

平台 SHALL 在管理库（management.db，Alembic 维护）维护一张 `skills` 主表，作为公共 skill 池的**权威元数据/索引源**。该表 SHALL 仅存元数据，skill 的实际内容（SKILL.md、脚本、子目录）SHALL 留在文件系统池中，不入库。`skills.name` SHALL 为主键。

#### Scenario: 主表仅存元数据不存内容
- **WHEN** 管理库迁移运行到最新版本
- **THEN** 存在 `skills` 表，含 `name`(PK) / `status` / `global_enabled` / `audit_verdict` / `audit_rules` / `forced` / `source` / `immutable_fields` / `current_version` / `archived_at` / `created_at` / `updated_at` 列
- **AND** 表中不含 SKILL.md 正文或脚本内容（内容仅在文件系统池）

### Requirement: catalog 合并治理状态与 skill 级 provenance

`skills` SHALL 合并原 `skill_admin_state` 的治理列（status / global_enabled / audit_verdict / audit_rules / forced / archived_at）与原 `skill_provenance` 的 skill 级列（`source ∈ {managed, adhoc}` / `immutable_fields` JSON），并 SHALL 新增 `current_version` 作为池 head 版本指针（顶替已废弃的死列 `last_deploy_at`）。

#### Scenario: 治理与 provenance 元数据同表读取
- **WHEN** 平台读取某 skill 的管理元数据
- **THEN** 其 `status` / `global_enabled` / `audit_verdict` / `source` / `immutable_fields` / `current_version` 均从同一 `skills` 行返回

#### Scenario: current_version 顶替 last_deploy_at
- **WHEN** 迁移完成后检查 `skills` 表结构
- **THEN** 存在 `current_version` 列、不存在 `last_deploy_at` 列

### Requirement: 池内 skill 保证有 catalog 行且缺行有默认兜底

scan/seed 路径 SHALL 为池内每个 skill upsert 一行 catalog 记录。当读取一个尚无 catalog 行的 skill 时，平台 SHALL 返回 active / global_enabled 的默认值以保持向后兼容。

#### Scenario: scan 时补齐 catalog 行
- **WHEN** 池中新增一个 skill 目录并触发 scan
- **THEN** `skills` 表为该 skill upsert 一行（默认 `source=adhoc`、`status=active`、`global_enabled=1`）

#### Scenario: 缺行读取走默认
- **WHEN** 读取一个在 `skills` 表中尚无行的 skill 名
- **THEN** 返回 `status=active` / `global_enabled=1` 的默认元数据，不报错

