## MODIFIED Requirements

### Requirement: Install bootstrap seeds explicit Platform and Agent homes

安装脚本 SHALL seed 明确的 Platform home 与默认 Agent home，而不是把 Platform home 根目录同时当成
Agent home。默认 Agent home SHALL be self-contained with `agent.yaml`, `.env`, and `data/`.

#### Scenario: Fresh install creates platform and default agent areas
- **WHEN** operator 在空 `FLEETENT_HOME` 运行安装
- **THEN** 安装创建平台运行所需 env/config
- **AND** 创建一个默认 Agent home，包含 `agent.yaml`、`.env` 和 `data/`
- **AND** 平台进程 env 不写入默认 Agent `.env`

#### Scenario: Existing operator files are preserved
- **WHEN** 平台 env 或 Agent home 文件已存在
- **THEN** 安装不覆盖已有 operator 文件
