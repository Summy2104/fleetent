## ADDED Requirements

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
