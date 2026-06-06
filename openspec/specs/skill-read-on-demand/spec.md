# skill-read-on-demand Specification

## Purpose
TBD - created by archiving change skill-read-on-demand. Update Purpose after archive.
## Requirements
### Requirement: 可用 Skill 清单注入(L1 感知)

注入链 MUST 在 system prompt 中始终拼入一份**已启用 Skill 的清单**,使 AI 感知有哪些 Skill 可用——无论用户输入是否提及。清单每项 MUST 含 Skill 的名称、一句话描述、以及其 SKILL.md 位置,并 MUST 附带一段指令告知 AI:当某 Skill 描述匹配任务时,调用 `read_skill` 工具按名加载其完整内容再遵循之。被禁用的 Skill(`disabled_skills` 配置命中,或 `enabled_by_default: false`)MUST 不出现在清单中。无任何可用 Skill 时,注入链 MUST 不拼入清单段(保持前缀最小)。

#### Scenario: 清单始终注入且含元数据
- **WHEN** 索引中存在已启用 Skill,构造任一请求的 system prompt
- **THEN** prompt 含 `<available_skills>` 清单,逐项列出每个已启用 Skill 的名称、描述、位置

#### Scenario: 禁用 Skill 不入清单
- **WHEN** 某 Skill 被 `disabled_skills` 命中或其 `enabled_by_default` 为 false
- **THEN** 该 Skill 不出现在清单中

#### Scenario: 无可用 Skill 不拼清单段
- **WHEN** 无任何已启用 Skill
- **THEN** system prompt 不含清单段

### Requirement: Skill 全文按需经工具加载

系统 MUST 提供 `read_skill(name)` 工具,返回指定 Skill 的完整 SKILL.md 内容;当无该名 Skill 时 MUST 返回明确的错误结果文本而非抛出。注入链 MUST NOT 基于关键词匹配自动把任何 Skill 的全文拼入 prompt——全文仅由 AI 主动调用 `read_skill` 时加载。

#### Scenario: 按名读取全文
- **WHEN** AI 对清单中某 Skill 调用 `read_skill` 并传其名称
- **THEN** 返回该 Skill 完整 SKILL.md 内容

#### Scenario: 未知名称返回错误文本
- **WHEN** `read_skill` 收到未注册的 Skill 名
- **THEN** 返回说明「无此 Skill」的错误结果文本,不中断 agent 循环

#### Scenario: 不再自动灌全文
- **WHEN** 用户输入的措辞本可关键词命中某 Skill
- **THEN** 注入链不因此自动加载或注入该 Skill 全文(仅清单存在;全文待 AI 调 `read_skill`)

### Requirement: 清单进稳定可缓存前缀

Skill 清单 MUST 与基础 system prompt 一起构成 system prompt 的**稳定前缀**(它仅随部署的 Skill 集变化、对逐条请求稳定),使自动前缀缓存可命中;逐请求可变内容(如记忆注入)MUST 排在该稳定前缀之后。

#### Scenario: 仅可变内容变化时前缀字节稳定
- **WHEN** 两次请求的 Skill 集相同、仅可变内容(记忆)不同
- **THEN** 承载「基础 system + 清单」的稳定前缀逐字节相同,可变内容位于其后


### Requirement: 清单注入受条数与字符预算约束

`available_skills_prompt` 渲染的 `<available_skills>` 清单 MUST 受条数上限（`max_skills`，默认 150）与字符上限（`max_chars`，默认 18000）约束，防止 skill 库增长后 system prompt 静默膨胀、吃掉 prompt cache 预算。

- 当 eligible skill 数超过 `max_skills` 时，清单 MUST 仅保留前 `max_skills` 个，并在指令之前置一行截断警告（含已显示数 N 与总数 M），使模型知晓清单不完整。
- 当渲染后的清单字符数超过 `max_chars` 时，MUST 切换为 compact 格式（仅 `name` + `location`，省去 `description`），在更小体积下保留可发现性。
- 默认值足够大，使现有部署（skill 数远小于 150 且字符远小于 18000）的渲染结果逐字节不变。
- 被截断而未列出的 skill 仍可经 `read_skill` 按名加载（清单是发现层，非授权边界）。

#### Scenario: 超条数上限时截断并警告
- **WHEN** eligible skill 数超过 `max_skills`
- **THEN** 清单仅含前 `max_skills` 个 skill
- **AND** 指令前出现一行截断警告，标注已显示数与总数

#### Scenario: 超字符上限时切 compact 格式
- **WHEN** 完整格式（含 description）渲染后超过 `max_chars`
- **THEN** 清单改用 compact 格式（仅 name + location，省 description）

#### Scenario: 小目录不受影响
- **WHEN** eligible skill 数远小于 `max_skills` 且渲染字符远小于 `max_chars`
- **THEN** 清单为完整格式、无截断警告，渲染结果与引入预算前完全一致

### Requirement: disable_model_invocation 隐藏 catalog 但保留 read_skill

当某 Skill 的 frontmatter 声明 `disable_model_invocation: true` 时，该 Skill MUST 从 `<available_skills>` catalog 隐藏（模型不主动发现它），但 `read_skill(name)` MUST 仍能按名加载其全文（供其他 Skill 或 hook 组合调用）。这与安全封禁（`audit_blocked`，read_skill 会拒）正交。

#### Scenario: disable_model_invocation 从 catalog 隐藏
- **WHEN** 某 Skill 声明 `disable_model_invocation: true`，构建 catalog
- **THEN** 该 Skill 的 name/description 不出现在 `<available_skills>` 中

#### Scenario: disable_model_invocation 的 skill 仍可 read_skill
- **WHEN** 对一个 `disable_model_invocation: true` 且未被 audit_blocked 的 Skill 调用 `read_skill`
- **THEN** 返回其 SKILL.md 正文（隐藏仅作用于 catalog 发现，不阻断按名加载）

### Requirement: requires_tools 渲染期按可用工具集过滤 catalog

当向 `available_skills_prompt` 传入当前会话的可用工具名集（`available_tools`）时，任一 Skill 若其 `requires_tools` 含不在该集合中的工具，MUST 从 catalog 隐藏。该过滤在渲染期进行（工具可用性每会话可变），与 scan 期的禁用判定正交。当未传入工具集（`available_tools=None`）时 MUST NOT 过滤（向后兼容）。

#### Scenario: 所需工具缺失时隐藏
- **WHEN** 某 Skill 声明 `requires_tools: [run_code]`，渲染时传入的可用工具集不含 `run_code`
- **THEN** 该 Skill 不出现在 catalog 中

#### Scenario: 所需工具齐备时显示
- **WHEN** 某 Skill 声明 `requires_tools: [run_code]`，渲染时传入的可用工具集含 `run_code`
- **THEN** 该 Skill 正常出现在 catalog 中

#### Scenario: 未传工具集时不过滤
- **WHEN** 渲染 catalog 未传入 `available_tools`（None）
- **THEN** requires_tools 不参与过滤，所有 eligible skill 照常渲染（向后兼容）
