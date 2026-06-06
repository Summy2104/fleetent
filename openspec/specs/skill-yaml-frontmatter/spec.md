# skill-yaml-frontmatter Specification

## Purpose
TBD - created by archiving change skill-yaml-frontmatter. Update Purpose after archive.
## Requirements
### Requirement: 标准 YAML frontmatter 解析

skill_registry SHALL 使用标准 YAML 解析器解析 SKILL.md 文件 `---` 边界之间的 frontmatter，正确支持标量、列表、布尔与数字类型，而非按行查找冒号的简易扫描。

#### Scenario: 解析列表型字段
- **WHEN** 某 SKILL.md 的 frontmatter 含 `tags: [crm, sales]` 或多行 `- item` 形式的列表
- **THEN** 该 Skill 的 `tags` 被解析为包含全部元素的列表，而非被截断的字符串

#### Scenario: 解析布尔与数字
- **WHEN** frontmatter 含 `enabled_by_default: false` 或数字型 `version`
- **THEN** 对应字段被解析为布尔/字符串等正确类型，而非裸字符串原样保留

### Requirement: 扩展元数据字段承载

skill_registry SHALL 在索引中识别并承载扩展字段 `tags`、`platforms`、`version`、`enabled_by_default`、`disable_model_invocation`、`requires_tools`、`required_env_vars`。未声明这些字段的 Skill MUST 使用确定的缺省值（`tags`/`platforms`/`requires_tools`/`required_env_vars` 为空列表、`version` 为空、`enabled_by_default` 为真、`disable_model_invocation` 为假），不影响其被匹配与加载。

- `disable_model_invocation`（bool）：作者声明该 Skill 不主动暴露给模型发现。
- `requires_tools`（list[str]）：该 Skill 依赖的工具名。
- `required_env_vars`（list，每项含 `name` 与可选 `optional`）：运行前需要的环境变量。

#### Scenario: 读取扩展字段
- **WHEN** 某 Skill 的 frontmatter 声明了 `tags` / `platforms` / `version` / `enabled_by_default` / `disable_model_invocation` / `requires_tools` / `required_env_vars`
- **THEN** 扫描后该 Skill 的索引条目保留这些字段的解析值

#### Scenario: 未声明扩展字段使用缺省值
- **WHEN** 某 Skill 仅声明 `name` 与 `description`，未声明任何扩展字段
- **THEN** 该 Skill 仍被正常索引，扩展字段取缺省值（含 `disable_model_invocation=false`、`requires_tools=[]`、`required_env_vars=[]`），匹配与加载行为与现状一致

### Requirement: Skill 运行就绪检查

skill_registry SHALL 提供 `skill_readiness(name)`，依据该 Skill 的 `required_env_vars` 报告缺失的非 `optional` 环境变量（不在进程 `os.environ` 中者）。该检查 MUST NOT 影响 catalog 渲染或 read_skill——它仅为运维就绪展示提供数据。

#### Scenario: 报告缺失的必需 env
- **WHEN** 某 Skill 声明 `required_env_vars` 含一个非 optional 的 `name` 且该变量未在环境中设置
- **THEN** `skill_readiness(name)` 的 `missing` 列表包含该变量名

#### Scenario: optional 与已设置的 env 不报缺失
- **WHEN** 某 Skill 的 required_env_vars 中某项标 `optional: true`，或对应变量已在环境中设置
- **THEN** `skill_readiness(name)` 的 `missing` 列表不含该变量名

### Requirement: 解析失败明确报警并跳过

当 SKILL.md 的 frontmatter 解析失败（缺失 `---` 边界、YAML 语法错误、或顶层不是映射）时，skill_registry MUST 记录一条包含该文件路径与失败原因的报警，并跳过该 Skill，不得静默地以空元数据将其纳入索引。

#### Scenario: 损坏的 YAML 报警并跳过
- **WHEN** 扫描到一个 frontmatter 含非法 YAML 语法的 SKILL.md
- **THEN** 记录一条含该文件路径的报警，且该 Skill 不出现在索引中

#### Scenario: 缺失 frontmatter 边界报警并跳过
- **WHEN** 扫描到一个不含闭合 `---` 边界或顶层不是映射的 SKILL.md
- **THEN** 记录一条含该文件路径的报警，且该 Skill 不被纳入索引

#### Scenario: 合法 frontmatter 不报警
- **WHEN** 扫描到一个 frontmatter 为合法 YAML 映射的 SKILL.md
- **THEN** 该 Skill 被正常解析并纳入索引，不产生解析失败报警

