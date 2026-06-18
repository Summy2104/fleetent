## MODIFIED Requirements

### Requirement: Install bootstrap seeds explicit Platform and Agent homes

安装脚本 SHALL seed 明确的 Platform home（含其配置模板与数据库），且 SHALL NOT 把 Platform home 根目录当成 Agent home。一键 `install.sh` SHALL NOT 再 seed 默认 Agent home（不再创建 `agents/default/`），改为在结尾打印创建 agent 的教程，引导 operator 自行 `fleetent agent init <agent-id>`——agent 创建与运行时安装解耦。

#### Scenario: install does not create a default Agent home
- **WHEN** `install.sh` completes
- **THEN** no default Agent config SHALL be created at `$FLEETENT_HOME/agents/default/` by the script
- **AND** no default Agent config SHALL be created at the Platform home root
- **AND** the script SHALL print a tutorial naming `fleetent agent init <agent-id>` as the way to create an agent

#### Scenario: Platform home is still seeded
- **WHEN** `install.sh` completes (platform component installed)
- **THEN** the Platform home SHALL be seeded (config templates + initialized database) as before, independent of any Agent home
