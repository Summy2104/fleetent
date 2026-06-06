## ADDED Requirements

### Requirement: Standalone agent 的 skill 索引建自其 home 的 skills 目录

`boot()` SHALL 从 agent 自己 home 的 `skills/` 子目录构建该进程的 skill 索引，使 standalone agent 的 skill catalog 自包含（不依赖进程 CWD 或 `FLEETENT_SKILLS_DIR`）。具体地，`boot()` SHALL 调用 `scan_skills(skills_dir=str(<home_dir>/"skills"))`。

当 `<home_dir>/skills/` 不存在时（如未经平台 materialize 的 `fleetent agent init` home），索引 SHALL 安全回退为仅含 builtin skills（不抛异常）。

#### Scenario: boot 从 home/skills 构建索引

- **WHEN** `<home>/skills/crm-ops/SKILL.md` 存在，`fleetent agent run` 启动该 home
- **THEN** 该进程的 skill 索引包含 "crm-ops"
- **AND** `available_skills_prompt` 渲染的 catalog 含 "crm-ops"（受 allowed_skills/disabled_skills 收窄后）

#### Scenario: home 无 skills 目录时安全

- **WHEN** agent home 没有 `skills/` 子目录，`fleetent agent run` 启动
- **THEN** boot 正常完成，skill 索引仅含 builtin skills，不抛异常

#### Scenario: skill 索引不依赖进程 CWD

- **WHEN** 两个不同 home 的 agent 进程在同一 CWD 启动，各自 home 的 `skills/` 内容不同
- **THEN** 每个进程的 skill 索引反映它自己 home 的 skills，互不影响
