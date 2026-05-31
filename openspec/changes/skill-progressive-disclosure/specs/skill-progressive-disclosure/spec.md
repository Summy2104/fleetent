## ADDED Requirements

### Requirement: L1 当前 agent 可用清单始终注入

skill_registry SHALL 产出**当前 agent 可用且启用**的 Skill「名称 + 一句话描述」清单（L1）——即对该次请求 `injectable`（过 agent 绑定 `check_skill_access` ∧ `enabled_by_default` ∧ 不在 `disabled_skills`）的 Skill。Skill 注入链 MUST 在每次请求处理前将该 L1 清单注入 system prompt，使 AI 始终**感知**有哪些 Skill 可用并松散遵循其一句话描述，即便关键词匹配未命中任何 Skill。L1 清单 MUST NOT 包含对当前 agent 不可用的 Skill（未在白名单 / 被 blocked / 被禁用）——否则会向 AI 展示它用不了的能力。当无可注入项时，L1 清单 MUST 为空，不向 system prompt 注入空清单噪声。

注入链 MUST 在 `run_sync` / `run_stream` / IM 渠道 `normalizer` 三处入口经**同一共享注入函数**产出 L1（与 L2），三处行为一致，不得遗漏 IM 渠道。

L1 仅让 AI **感知**可用 Skill；本 capability 不提供让 AI 主动拉取某个未命中 Skill 之 L2 全文的 on-demand 工具，注入仍由关键词 `match` 驱动。

#### Scenario: 未命中时仍注入当前 agent 可用的 L1 清单
- **WHEN** 用户输入未关键词命中任何 Skill，且索引中存在若干对当前 agent 可注入的 Skill
- **THEN** system prompt 包含这些 Skill 的「名称+描述」清单（L1），但不包含任何 Skill 的完整正文

#### Scenario: L1 清单按 agent 绑定与启用状态过滤
- **WHEN** 索引中存在某 Skill，但它不在当前 agent 的 `allowed_skills`、或在 `blocked_skills`、或被 `disabled_skills` / `enabled_by_default=false` 禁用
- **THEN** 该 Skill 不出现在注入的 L1 清单中

#### Scenario: 三处注入入口的 L1/L2 行为一致
- **WHEN** 同一请求分别经 `run_sync`、`run_stream`、IM 渠道 `normalizer` 处理
- **THEN** 三处注入的 L1 清单与 L2 全文遵循相同的可见性与命中规则，不出现某入口缺少 L1 的分叉

#### Scenario: 无可注入项时不注入清单
- **WHEN** 对当前 agent 没有任何可注入的 Skill（索引为空，或全部被过滤）
- **THEN** L1 清单为空，system prompt 不因 Skill 注入而改变

### Requirement: L2 全文按需注入

当关键词匹配命中某 Skill **且**该 Skill 通过当前 agent 的绑定门控（`check_skill_access`）时，Skill 注入链 SHALL 加载该 Skill 的完整 SKILL.md 正文（L2）并注入 system prompt。L2 全文 MUST 仅针对命中且过门控的 Skill 加载，未命中或未过门控的 Skill MUST NOT 注入其正文。L1 与 L2 MUST 共享同一可注入性边界（`injectable` 谓词）——AI 在 L1 看得见的 Skill，正是它（命中后）真能注入 L2 的那批。

#### Scenario: 命中时同时注入 L1 清单与 L2 全文
- **WHEN** 用户输入关键词命中某对当前 agent 可注入的 Skill
- **THEN** system prompt 同时包含当前 agent 可用的 L1 清单与该命中 Skill 的完整正文（L2）

#### Scenario: 未命中的 Skill 不注入正文
- **WHEN** 索引中存在某对当前 agent 可注入的 Skill 但用户输入未命中其关键词
- **THEN** system prompt 不包含该 Skill 的完整正文（L2），仅在 L1 清单中保留其名称与描述

### Requirement: L3 附属资源延迟加载边界

SKILL.md 中引用的附属资源文件（L3）MUST NOT 随 L2 全文注入 system prompt。L3 资源 SHALL 由 AI 经既有文件读取工具按需获取，注入链不主动读取并拼入任何被引用的附属文件内容。

#### Scenario: 附属文件内容不进入 prompt
- **WHEN** 某命中 Skill 的 SKILL.md 引用了附属资源文件，且该 Skill 被注入
- **THEN** system prompt 仅包含 SKILL.md 正文，不包含被引用附属文件的内容
