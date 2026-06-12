## MODIFIED Requirements

### Requirement: 可用 Skill 清单注入(L1 感知)

注入链 MUST 在 system prompt 中始终拼入一份**已启用 Skill 的清单**,使 AI 感知有哪些 Skill 可用——无论用户输入是否提及。清单每项 MUST 含 Skill 的名称、一句话描述、以及其 SKILL.md 位置,并 MUST 附带一段指令告知 AI:当某 Skill 描述匹配任务时,调用 `read_skill` 工具按名加载其完整内容再遵循之。该指令段 MUST 额外注明 **skill 脚本须经容器内执行面(`run_code`)运行,且脚本内路径以 `$SKILLS_DIR`(= `/workspace/skills`)为根**,使 AI 不按宿主绝对路径运行 skill 脚本。该指引为对全体 skill 一致的固定文本(不随单个 skill 变化),保持清单段作为稳定前缀的字节稳定性(见「清单进稳定可缓存前缀」)。被禁用的 Skill(`disabled_skills` 配置命中,或 `enabled_by_default: false`)MUST 不出现在清单中。无任何可用 Skill 时,注入链 MUST 不拼入清单段(保持前缀最小)。

#### Scenario: 清单始终注入且含元数据
- **WHEN** 索引中存在已启用 Skill,构造任一请求的 system prompt
- **THEN** prompt 含 `<available_skills>` 清单,逐项列出每个已启用 Skill 的名称、描述、位置

#### Scenario: 清单指令注入执行面与 SKILLS_DIR 根
- **WHEN** 索引中存在已启用 Skill,渲染清单的指令段
- **THEN** 指令段注明 skill 脚本经容器内执行面(`run_code`)运行、路径以 `$SKILLS_DIR` 为根

#### Scenario: 禁用 Skill 不入清单
- **WHEN** 某 Skill 被 `disabled_skills` 命中或其 `enabled_by_default` 为 false
- **THEN** 该 Skill 不出现在清单中

#### Scenario: 无可用 Skill 不拼清单段
- **WHEN** 无任何已启用 Skill
- **THEN** system prompt 不含清单段

### Requirement: Skill 全文按需经工具加载

系统 MUST 提供 `read_skill(name)` 工具,返回指定 Skill 的完整 SKILL.md 内容;当无该名 Skill 时 MUST 返回明确的错误结果文本而非抛出。`read_skill` 的返回 MUST 在 SKILL.md 正文之外附带一段简短指引,注明**该 Skill 的脚本须经容器内执行面(`run_code`)运行、脚本内路径以 `$SKILLS_DIR` 为根**,使 AI 加载全文后按统一 /workspace 世界执行其脚本。注入链 MUST NOT 基于关键词匹配自动把任何 Skill 的全文拼入 prompt——全文仅由 AI 主动调用 `read_skill` 时加载。

#### Scenario: 按名读取全文
- **WHEN** AI 对清单中某 Skill 调用 `read_skill` 并传其名称
- **THEN** 返回该 Skill 完整 SKILL.md 内容

#### Scenario: 返回附带执行面与路径指引
- **WHEN** AI 对一个含脚本的 Skill 调用 `read_skill` 成功加载
- **THEN** 返回内容附带指引,注明脚本经容器内执行面(`run_code`)运行、路径以 `$SKILLS_DIR` 为根

#### Scenario: 未知名称返回错误文本
- **WHEN** `read_skill` 收到未注册的 Skill 名
- **THEN** 返回说明「无此 Skill」的错误结果文本,不中断 agent 循环

#### Scenario: 不再自动灌全文
- **WHEN** 用户输入的措辞本可关键词命中某 Skill
- **THEN** 注入链不因此自动加载或注入该 Skill 全文(仅清单存在;全文待 AI 调 `read_skill`)
