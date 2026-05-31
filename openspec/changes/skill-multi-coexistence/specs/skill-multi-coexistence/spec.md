## ADDED Requirements

### Requirement: 确定性返回全部命中的 Skill

skill_registry SHALL 提供返回**全部**关键词命中 Skill 的匹配能力，而非仅返回首个命中。命中集合的顺序 MUST 是确定的、可解释的（不依赖扫描时的目录遍历/插入顺序），以保证同一输入下选定结果可复现。

#### Scenario: 多个命中全部返回
- **WHEN** 用户输入同时关键词命中两个 Skill 的描述
- **THEN** 匹配结果包含这两个 Skill 的名称

#### Scenario: 命中顺序确定且不依赖扫描顺序
- **WHEN** 以不同扫描插入顺序索引同一组 Skill，并以同一输入匹配
- **THEN** 返回的命中顺序一致（确定性），不随插入顺序变化

#### Scenario: 无命中返回空
- **WHEN** 用户输入未命中任何 Skill 的关键词
- **THEN** 匹配结果为空集合

### Requirement: 多命中时 L1 共存、L2 单注入

当一次请求命中多个非互斥 Skill 时，注入链 SHALL 让全部命中 Skill 的 L1 摘要共存于 system prompt，而 L2 全文 MUST 仅注入其中确定性选定的一个，避免多篇全文同时注入导致 context 膨胀。

#### Scenario: 多命中的 L1 摘要共存
- **WHEN** 用户输入同时命中两个非互斥 Skill
- **THEN** system prompt 同时包含这两个 Skill 的名称与描述（L1 摘要）

#### Scenario: 多命中只注入一个 L2 全文
- **WHEN** 用户输入同时命中两个非互斥 Skill
- **THEN** system prompt 仅包含确定性选定的那一个 Skill 的完整正文（L2），不同时注入两篇全文

### Requirement: 互斥 Skill 命中时询问用户选择

注入链 SHALL 支持 Skill 经 frontmatter 声明 `exclusive`（缺省为假）。当一次请求的命中集合中存在 `exclusive` 为真的 Skill 时，注入链 MUST NOT 擅自选定并注入任一命中 Skill 的 L2 全文，而是产出一个包含候选 Skill 名列表的结构化询问信号（与 system prompt 一同返回，候选 Skill 名可被调用方读取），交由调用方向用户询问；信号不绑定具体交互通道（CLI / 流式 SSE 各自呈现）。

#### Scenario: 互斥命中不擅自注入而是产出含候选名的询问信号
- **WHEN** 用户输入命中的 Skill 集合中存在一个 `exclusive: true` 的 Skill
- **THEN** 注入链不注入任何命中 Skill 的 L2 全文，并产出一个询问选择信号，其候选列表包含命中集合中的 Skill 名

#### Scenario: 非互斥命中不触发询问
- **WHEN** 用户输入命中的所有 Skill 的 `exclusive` 均为假
- **THEN** 注入链不产出询问信号，按多命中策略注入 L1 共存与单个 L2 全文
