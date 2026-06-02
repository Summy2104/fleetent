## ADDED Requirements

### Requirement: KnowledgeBridge migration plan
系统 SHALL 在实现 fleetent knowledge-base 运行时代码前，产出 `knowledge-bridge` 到 fleetent 的迁移计划。

#### Scenario: Migration plan document exists
- **WHEN** 本 change 完成
- **THEN** 仓库包含 `docs/knowledge-bridge-migration-plan.md`

#### Scenario: Migration plan links from capability doc
- **WHEN** 读者查看 `docs/capabilities/knowledge-base.md`
- **THEN** 文档链接到 migration plan，并说明 knowledge-base 将按拆分 specs 渐进实现

### Requirement: Migration asset classification
迁移计划 SHALL 将 `knowledge-bridge` 资产分为可直接迁移、可参考但需重写、暂缓迁移和不迁移。

#### Scenario: Direct migration candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到可直接迁移的 parser、connector、sync 或 audit 候选能力

#### Scenario: Rewrite candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到需要重写的 vector store、embedding、chunking、retrieval 或 query scope 能力及原因

#### Scenario: Deferred and rejected candidates are listed
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到暂缓迁移和不迁移的能力及原因

### Requirement: Fleetent constraint mapping
迁移计划 SHALL 明确 `knowledge-bridge` 与 fleetent 约束之间的差异。

#### Scenario: Disallowed dependencies are documented
- **WHEN** 读者查看 migration plan
- **THEN** LlamaIndex、LanceDB direct dependency、OpenAI Embeddings default 和 standalone REST service boundary 的处理方式被明确说明

### Requirement: Knowledge-base spec split
迁移计划 SHALL 输出 fleetent knowledge-base 后续 specs 的拆分顺序、边界和依赖。

#### Scenario: Core spec is defined
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到 `knowledge-base-core` 的最小范围和不包含范围

#### Scenario: Follow-up specs are defined
- **WHEN** 读者查看 migration plan
- **THEN** 可以看到 parser、connector、hybrid search、graph search 和 sync planner 后续 specs 的建议顺序
