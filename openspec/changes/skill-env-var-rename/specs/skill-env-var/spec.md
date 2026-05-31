## ADDED Requirements

### Requirement: 通过 FLEETENT_SKILLS_DIR 覆盖 skills 目录

当未向扫描显式传入 skills 目录路径时，skill_registry SHALL 从环境变量 `FLEETENT_SKILLS_DIR` 读取 skills 目录路径；该环境变量未设置时 MUST 回落到默认值 `./skills`。skill_registry MUST NOT 再读取旧变量名 `MINI_AGENT_SKILLS_DIR`。

#### Scenario: 设置 FLEETENT_SKILLS_DIR 时使用该路径
- **WHEN** 设置了环境变量 `FLEETENT_SKILLS_DIR` 且未向扫描显式传入路径
- **THEN** 扫描使用 `FLEETENT_SKILLS_DIR` 指定的目录

#### Scenario: 未设置时回落默认目录
- **WHEN** 未设置 `FLEETENT_SKILLS_DIR` 且未向扫描显式传入路径
- **THEN** 扫描使用默认目录 `./skills`

#### Scenario: 旧变量名不再生效
- **WHEN** 仅设置了旧变量名 `MINI_AGENT_SKILLS_DIR`、未设置 `FLEETENT_SKILLS_DIR` 且未显式传入路径
- **THEN** 扫描不使用 `MINI_AGENT_SKILLS_DIR` 的值，而是回落到默认目录 `./skills`

#### Scenario: 显式传入路径优先于环境变量
- **WHEN** 向扫描显式传入 skills 目录路径，同时环境变量 `FLEETENT_SKILLS_DIR` 也已设置
- **THEN** 扫描使用显式传入的路径，忽略环境变量
