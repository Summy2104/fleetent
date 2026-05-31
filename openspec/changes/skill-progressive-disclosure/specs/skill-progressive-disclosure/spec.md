## ADDED Requirements

### Requirement: L1 全量摘要始终注入

skill_registry SHALL 产出全量已索引 Skill 的「名称 + 一句话描述」清单（L1）。Skill 注入链 MUST 在每次请求处理前将该 L1 清单注入 system prompt，使 AI 始终感知有哪些 Skill 可用，即便关键词匹配未命中任何 Skill。当索引为空时，L1 清单 MUST 为空，不向 system prompt 注入空清单噪声。

#### Scenario: 未命中时仍注入 L1 清单
- **WHEN** 用户输入未关键词命中任何 Skill，且索引中存在若干 Skill
- **THEN** system prompt 包含全量 Skill 的「名称+描述」清单（L1），但不包含任何 Skill 的完整正文

#### Scenario: 索引为空时不注入清单
- **WHEN** 索引中没有任何 Skill
- **THEN** L1 清单为空，system prompt 不因 Skill 注入而改变

### Requirement: L2 全文按需注入

当关键词匹配命中某 Skill 时，Skill 注入链 SHALL 加载该 Skill 的完整 SKILL.md 正文（L2）并注入 system prompt。L2 全文 MUST 仅针对命中的 Skill 加载，未命中的 Skill MUST NOT 注入其正文。

#### Scenario: 命中时同时注入 L1 清单与 L2 全文
- **WHEN** 用户输入关键词命中某 Skill
- **THEN** system prompt 同时包含全量 L1 清单与该命中 Skill 的完整正文（L2）

#### Scenario: 未命中的 Skill 不注入正文
- **WHEN** 索引中存在某 Skill 但用户输入未命中其关键词
- **THEN** system prompt 不包含该 Skill 的完整正文（L2），仅在 L1 清单中保留其名称与描述

### Requirement: L3 附属资源延迟加载边界

SKILL.md 中引用的附属资源文件（L3）MUST NOT 随 L2 全文注入 system prompt。L3 资源 SHALL 由 AI 经既有文件读取工具按需获取，注入链不主动读取并拼入任何被引用的附属文件内容。

#### Scenario: 附属文件内容不进入 prompt
- **WHEN** 某命中 Skill 的 SKILL.md 引用了附属资源文件，且该 Skill 被注入
- **THEN** system prompt 仅包含 SKILL.md 正文，不包含被引用附属文件的内容
