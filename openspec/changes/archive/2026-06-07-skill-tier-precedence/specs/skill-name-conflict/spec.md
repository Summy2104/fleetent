## MODIFIED Requirements

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
