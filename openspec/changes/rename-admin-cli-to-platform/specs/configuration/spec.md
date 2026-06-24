## MODIFIED Requirements

### Requirement: Local configuration initialization

系统 SHALL 提供 `fleetent platform init-config` 作为 Platform home 配置初始化入口。

#### Scenario: Init config creates local Platform files
- **WHEN** operator 运行 `fleetent platform init-config`
- **THEN** 系统从 `.env.example` 创建 `.env`
- **AND** 从 `platform.yaml.example` 创建 `platform.yaml`
- **AND** 创建 `data/`、`data/logs/`、`data/diagnostics/` 和 `secrets/`

#### Scenario: Init config does not overwrite by default
- **WHEN** 目标文件已经存在
- **AND** operator 未传 `--force`
- **THEN** init-config 跳过该文件
- **AND** 输出说明该文件已存在

#### Scenario: Init config dry run does not write
- **WHEN** operator 运行 `fleetent platform init-config --dry-run`
- **THEN** 系统输出将创建、跳过或覆盖的路径
- **AND** 不写入文件系统

#### Scenario: Init config force overwrites generated files
- **WHEN** operator 运行 `fleetent platform init-config --force`
- **THEN** 系统覆盖 `.env` 和 `platform.yaml`
- **AND** 不删除未知文件
- **AND** 不生成任何真实 secret 文件
