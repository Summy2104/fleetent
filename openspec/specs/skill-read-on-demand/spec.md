# skill-read-on-demand Specification

## Purpose
TBD - created by archiving change skill-read-on-demand. Update Purpose after archive.
## Requirements
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

### Requirement: read_skill 支持按相对路径读取 skill 支撑文件

`read_skill` MUST 接受一个可选的 `file_path` 参数：省略时行为完全不变（返回该 skill 的 SKILL.md 全文并附 `$SKILLS_DIR`/执行面指引）；给出相对路径时 MUST 返回该 skill 目录下对应文件（`references/`、`examples/` 等）的内容。路径解析 MUST 限定在该 skill 目录之内——解析后落到目录之外的路径 MUST 被拒绝并返回明确错误文本（不抛异常、不读到目录外文件）。文件不存在时 MUST 返回明确错误文本。被静态注入审计标记 `audit_blocked` 的 skill，其支撑文件读取 MUST 与 SKILL.md 全文一样被拒绝。

#### Scenario: 按相对路径读取支撑文件
- **WHEN** AI 对某 skill 调用 `read_skill` 并传 `file_path="references/api.md"`，且该文件存在于 skill 目录下
- **THEN** 返回 `references/api.md` 的内容

#### Scenario: 省略 file_path 行为不变
- **WHEN** AI 对某 skill 调用 `read_skill` 不传 `file_path`
- **THEN** 返回该 skill 的 SKILL.md 全文并附既有执行面/路径指引（与本变更前字节一致）

#### Scenario: 路径遍历被拒绝
- **WHEN** AI 对某 skill 调用 `read_skill` 并传一个解析后落到 skill 目录之外的 `file_path`（如 `../../etc/passwd`）
- **THEN** 返回说明路径越界的错误文本，不读取目录外任何文件

#### Scenario: 不存在的支撑文件返回错误文本
- **WHEN** `file_path` 指向 skill 目录下不存在的文件
- **THEN** 返回说明文件不存在的错误文本，不中断 agent 循环

#### Scenario: audit_blocked skill 的支撑文件不可达
- **WHEN** 对一个被标记 `audit_blocked` 的 skill 传 `file_path` 调用 `read_skill`
- **THEN** 返回因安全审计被拒的明确文本，不返回该文件内容

### Requirement: 提供 list_skills 按需查询工具

系统 MUST 提供 `list_skills(keyword=None, category=None)` 工具，返回已索引 skill 的轻量列表（每项含 name 与 description）。`keyword` MUST 做大小写无关子串过滤，命中 skill 的 name、description 或 tags 任一即纳入；`category` MUST 按 skill 的 tags 过滤（fleetent skill 无独立 category 字段，category 语义即按 tag 归类）。两者均省略时 MUST 返回全部可见 skill。该工具 MUST 默认排除被 `audit_blocked` 或 author-disabled 的 skill（与 catalog 资格一致），且 MUST NOT 返回 SKILL.md 正文（仅元数据）。该工具是常驻 catalog 被 cap/截断或需按主题过滤时的按需查询面，MUST NOT 改变 `available_skills_prompt` 既有的 catalog 注入行为。

#### Scenario: 关键词过滤
- **WHEN** AI 调用 `list_skills(keyword="github")`
- **THEN** 返回 name/description/tags 命中 "github"（大小写无关）的 skill 列表，每项含 name 与 description

#### Scenario: 类别按 tag 过滤
- **WHEN** AI 调用 `list_skills(category="data")` 且某 skill 的 tags 含 "data"
- **THEN** 该 skill 出现在结果中

#### Scenario: 无参返回全部可见 skill
- **WHEN** AI 调用 `list_skills()` 不带任何过滤
- **THEN** 返回全部未被禁用/未被审计拒绝的 skill 的 name+description 列表

#### Scenario: 排除被审计拒绝的 skill
- **WHEN** 索引中存在一个 `audit_blocked` 的 skill，AI 调用 `list_skills()`
- **THEN** 该 skill 不出现在结果中

#### Scenario: 不返回正文
- **WHEN** AI 调用 `list_skills(keyword=...)`
- **THEN** 每个结果项只含 name 与 description，不含 SKILL.md 正文

