## ADDED Requirements

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
