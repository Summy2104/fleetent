## ADDED Requirements

### Requirement: Intelligence capability status documentation
系统 SHALL 保持常乐负责模块的 capability 文档与已归档 OpenSpec changes 和当前实现状态一致。

#### Scenario: Status sections are current
- **WHEN** 读者查看 memory、long-term-ctx、knowledge-base、vector-store、reflection、observability 或 deployment capability 文档
- **THEN** 文档说明当前已完成的 foundation、尚未完成的缺口和下一批候选 specs

#### Scenario: Runtime behavior is unchanged
- **WHEN** 本 change 完成
- **THEN** 仓库不包含运行时代码或数据库 schema 变更
