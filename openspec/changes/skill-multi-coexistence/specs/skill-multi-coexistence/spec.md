## ADDED Requirements

### Requirement: 确定性返回全部命中的 Skill 并保留禁用过滤

skill_registry SHALL 提供返回**全部**关键词命中 Skill 的匹配能力（`match_all`），而非仅返回首个命中。命中集合的顺序 MUST 是确定的、可解释的（不依赖扫描时的目录遍历/插入顺序）。`match_all` MUST 沿用现有 `match` 的禁用过滤：`enabled_by_default` 为假、或名在 `disabled_skills`（入参或部署配置）内的 Skill MUST NOT 出现在结果中，以保证注入链由 `match` 切换到 `match_all` 不丢失既有的禁用过滤。

#### Scenario: 多个命中全部返回
- **WHEN** 用户输入同时关键词命中两个未被禁用的 Skill 的描述
- **THEN** 匹配结果包含这两个 Skill 的名称

#### Scenario: 命中顺序确定且不依赖扫描顺序
- **WHEN** 以不同扫描插入顺序索引同一组 Skill，并以同一输入匹配
- **THEN** 返回的命中顺序一致（确定性），不随插入顺序变化

#### Scenario: 禁用的命中 Skill 被过滤
- **WHEN** 一个被关键词命中的 Skill 的 `enabled_by_default` 为假，或其名在 `disabled_skills` 内
- **THEN** 该 Skill 不出现在 `match_all` 的结果中（与 `match` 的过滤一致）

#### Scenario: 无命中返回空
- **WHEN** 用户输入未命中任何 Skill 的关键词
- **THEN** 匹配结果为空集合

### Requirement: 多命中时 L1 共存、L2 单注入、逐候选保留绑定门控

当一次请求命中多个 Skill 时，注入链 SHALL 让全部命中且**逐候选**通过 agent 绑定门控（`check_skill_access`，依 `allowed_skills` / `blocked_skills`）的 Skill 的 L1 摘要共存于 system prompt，而 L2 全文 MUST 仅注入其中确定性选定的一个，避免多篇全文同时注入导致 context 膨胀。绑定门控 MUST 逐候选应用——任一不在白名单（或在黑名单）的命中 Skill MUST NOT 被注入，也 MUST NOT 被选作 L2。

#### Scenario: 多命中的 L1 摘要共存
- **WHEN** 用户输入同时命中两个非互斥 Skill
- **THEN** system prompt 同时包含这两个 Skill 的名称与描述（L1 摘要）

#### Scenario: 多命中只注入一个 L2 全文
- **WHEN** 用户输入同时命中两个非互斥 Skill
- **THEN** system prompt 仅包含确定性选定的那一个 Skill 的完整正文（L2），不同时注入两篇全文

#### Scenario: 越权命中的 Skill 不被注入也不被选作 L2
- **WHEN** 用户输入命中两个 Skill，但其中一个不在当前 agent 的 `allowed_skills` 白名单内（或在 `blocked_skills` 内）
- **THEN** 该越权 Skill 的 L1/L2 均不被注入，L2 在剩余通过门控的命中中确定性选定

### Requirement: 互斥 Skill 真冲突时询问用户选择

注入链 SHALL 支持 Skill 经 frontmatter 声明 `exclusive`（缺省为假）。**仅当**一次请求中通过门控的命中数 > 1 且其中存在 `exclusive` 为真的 Skill（即真有冲突）时，注入链 MUST NOT 擅自选定并注入任一命中 Skill 的 L2 全文，而是产出一个包含候选 Skill 名列表的结构化询问信号（与 system prompt 一同返回，候选 Skill 名可被调用方读取），交由调用方向用户询问；信号不绑定具体交互通道（CLI / 流式 SSE / IM 各自呈现）。当一个 `exclusive` 为真的 Skill **单独命中**（无其他命中冲突对象）时，注入链 MUST 按普通命中正常注入其 L2 全文，且 MUST NOT 产出询问信号。

#### Scenario: 真冲突命中不擅自注入而是产出含候选名的询问信号
- **WHEN** 用户输入命中的（通过门控的）Skill 集合数量大于一，且其中存在一个 `exclusive: true` 的 Skill
- **THEN** 注入链不注入任何命中 Skill 的 L2 全文，并产出一个询问选择信号，其候选列表包含命中集合中的 Skill 名

#### Scenario: 单个 exclusive Skill 独自命中时正常注入、不询问
- **WHEN** 用户输入仅命中一个 Skill，且该 Skill 的 `exclusive` 为真
- **THEN** 注入链正常注入该 Skill 的 L2 全文，并且不产出询问信号

#### Scenario: 非互斥命中不触发询问
- **WHEN** 用户输入命中的所有 Skill 的 `exclusive` 均为假
- **THEN** 注入链不产出询问信号，按多命中策略注入 L1 共存与单个 L2 全文

### Requirement: 用户选定后回灌选中 Skill 的 L2

询问信号产出后，注入链 SHALL 提供让用户选定的 Skill 生效的回灌语义：调用方携用户选定的 Skill 名再次进入注入辅助（将命中集合收敛为该单个候选）后，注入链 MUST 对该选定 Skill 正常注入其 L2 全文并且不再产出询问信号；选定 Skill 若未通过 agent 绑定门控或禁用过滤，则视为无效选择，MUST NOT 注入。作为退化语义，当上层不实现结构化选择回传时，用户可改措辞使下一轮输入只命中单个 Skill，从而走单命中正常注入分支。

#### Scenario: 选定的 Skill 被回灌注入 L2
- **WHEN** 调用方携用户从候选中选定的一个 Skill 名再次进入注入辅助
- **THEN** system prompt 包含该选定 Skill 的 L2 全文，且不再产出询问信号

#### Scenario: 选定未通过门控的 Skill 不被注入
- **WHEN** 用户选定的 Skill 名未通过 agent 绑定门控或被禁用过滤
- **THEN** 该 Skill 的 L2 不被注入
