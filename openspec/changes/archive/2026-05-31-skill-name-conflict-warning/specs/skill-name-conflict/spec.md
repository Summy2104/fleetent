## ADDED Requirements

### Requirement: 同名 Skill 冲突报警

扫描过程中当两个或更多 `SKILL.md` 解析出相同的 Skill `name` 时，skill_registry MUST 记录一条包含该 name 与冲突文件路径的报警，而不得静默覆盖。

#### Scenario: 检测到同名冲突时报警
- **WHEN** 扫描发现两个不同路径的 `SKILL.md` 解析出相同的 `name`
- **THEN** 记录一条含该 name 与两个冲突文件路径的报警

#### Scenario: 多重同名逐对报警
- **WHEN** 三个或更多 `SKILL.md` 解析出同一个 `name`
- **THEN** 每个落选的同名条目都记录一条报警，便于排查全部碰撞

### Requirement: 确定性选定唯一胜出者

发生同名冲突时，skill_registry MUST 按确定性规则（`SKILL.md` 路径字符串排序，靠前者胜出）选定唯一一个条目纳入索引，结果不得依赖文件系统遍历顺序或运行平台。每个 name 在索引中 MUST 只保留一个条目。

#### Scenario: 路径排序靠前者胜出
- **WHEN** 同一个 name 对应路径 `skills/a/SKILL.md` 与 `skills/b/SKILL.md`
- **THEN** 索引中该 name 保留路径排序靠前的条目，无论两者被扫描到的先后

#### Scenario: 选定结果与扫描顺序无关
- **WHEN** 同名冲突的两个 Skill 以任意顺序被扫描发现
- **THEN** 最终索引中保留的胜出者一致，由确定性规则决定而非到达顺序

### Requirement: 无冲突时行为不变

未发生同名冲突时，skill_registry 的索引内容与匹配/加载行为 MUST 与引入冲突检测前完全一致，且不产生冲突报警。

#### Scenario: 无同名时不报警
- **WHEN** 扫描到的所有 Skill 名称互不相同
- **THEN** 索引包含全部 Skill，不产生任何同名冲突报警
