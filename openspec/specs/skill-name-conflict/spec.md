# skill-name-conflict Specification

## Purpose
TBD - created by archiving change skill-name-conflict-warning. Update Purpose after archive.
## Requirements
### Requirement: 同名 Skill 冲突报警

扫描过程中当两个或更多 `SKILL.md` 解析出相同的 Skill `name` 时，skill_registry MUST 记录一条包含该 name 与冲突文件路径的报警，而不得静默覆盖。

#### Scenario: 检测到同名冲突时报警
- **WHEN** 扫描发现两个不同路径的 `SKILL.md` 解析出相同的 `name`
- **THEN** 记录一条含该 name 与两个冲突文件路径的报警

#### Scenario: 多重同名逐对报警
- **WHEN** 三个或更多 `SKILL.md` 解析出同一个 `name`
- **THEN** 每个落选的同名条目都记录一条报警，便于排查全部碰撞

### Requirement: 确定性选定唯一胜出者

发生同名冲突时，skill_registry MUST 按确定性规则选定唯一一个条目纳入索引，结果不得依赖文件系统遍历顺序或运行平台。每个 name 在索引中 MUST 只保留一个条目。

选定规则按以下优先级：

1. **层级优先**：当冲突双方来源不同（一个 builtin、一个 user）时，user skill（`builtin=False`）MUST 胜出，使 operator 能用自定义 user skill 可预测地覆盖同名 builtin skill —— 与路径排序无关。
2. **同层路径排序**：当冲突双方来源相同（都是 builtin 或都是 user）时，MUST 按 `SKILL.md` 路径字符串排序、靠前者胜出。

冲突报警 MUST 标注本次是否为层级覆盖（`tier_override`），以便运维区分"user 覆盖 builtin"（预期）与"同层重名"（可能为配置错误）。

#### Scenario: user skill 覆盖同名 builtin skill
- **WHEN** 一个 builtin skill 与一个 user skill 同名，且 builtin 的路径字符串排序靠前
- **THEN** 索引中保留 user skill 的条目（层级优先于路径排序）
- **AND** 冲突报警标注 `tier_override` 为真

#### Scenario: 同层冲突仍按路径排序
- **WHEN** 同一个 name 对应两个 user skill，路径 `skills/a/SKILL.md` 与 `skills/b/SKILL.md`
- **THEN** 索引中保留路径排序靠前的条目（同层规则不变）
- **AND** 冲突报警标注 `tier_override` 为假

#### Scenario: 选定结果与扫描顺序无关
- **WHEN** 同名冲突的两个 Skill 以任意顺序被扫描发现
- **THEN** 最终索引中保留的胜出者一致，由层级优先 + 同层路径排序的确定性规则决定，而非到达顺序

### Requirement: 无冲突时行为不变

未发生同名冲突时，skill_registry 的索引内容与匹配/加载行为 MUST 与引入冲突检测前完全一致，且不产生冲突报警。

#### Scenario: 无同名时不报警
- **WHEN** 扫描到的所有 Skill 名称互不相同
- **THEN** 索引包含全部 Skill，不产生任何同名冲突报警

