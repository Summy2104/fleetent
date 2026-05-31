## ADDED Requirements

### Requirement: 递归扫描任意层级 SKILL.md

skill_registry 的扫描 SHALL 递归遍历 `skills/` 目录下的所有子目录，发现并索引任意层级中的 `SKILL.md` 文件，而不再仅限于一级子目录。

#### Scenario: 深层嵌套 Skill 被发现
- **WHEN** `skills/` 下存在多层级路径（如 `skills/crm/contracts/SKILL.md`）中的 Skill
- **THEN** 该 Skill 被扫描发现并纳入索引，可被匹配与加载

#### Scenario: 混合层级全部纳入
- **WHEN** `skills/` 同时包含一级子目录与更深层级的 `SKILL.md`
- **THEN** 所有层级的 Skill 均被纳入索引，无遗漏

### Requirement: 单层扫描行为保持兼容

递归扫描 MUST 保持原有单层 Skill 的发现、frontmatter 解析与 name 回落行为不变；`skills/` 目录不存在时扫描 MUST 安全返回而不抛异常。

#### Scenario: 一级目录 Skill 行为不变
- **WHEN** `skills/` 下存在一级子目录形式的 `SKILL.md`（与现状一致）
- **THEN** 该 Skill 的发现、解析与索引结果与递归扫描引入前一致

#### Scenario: 目录不存在安全返回
- **WHEN** 配置的 `skills/` 目录不存在
- **THEN** 扫描直接返回，索引为空，不抛出异常
