## MODIFIED Requirements

### Requirement: Configuration templates
install script SHALL 在 `FLEETENT_HOME` 根目录（扁平布局，无 `config/` 子目录）从模板创建运行所需文件，且不覆盖 operator 已有内容：seed 根目录 `agent.yaml`（自包含单体 agent 配置）与 `.env`。全局配置文件（settings/mcp/mcp.servers）不再 seed —— 各加载器在其缺失时回退默认值。

#### Scenario: Agent config and env seeded at home root on fresh install
- **WHEN** `FLEETENT_HOME` 下不存在 `agent.yaml` 或 `.env`
- **THEN** script 从 `config/agent.yaml.example` 创建 `$FLEETENT_HOME/agent.yaml`
- **AND** 从 `.env.example` 创建 `$FLEETENT_HOME/.env`
- **AND** 不创建 `$FLEETENT_HOME/config/` 子目录、不拷贝全局 `config/*.yaml`

#### Scenario: Existing agent.yaml or .env is preserved
- **WHEN** `$FLEETENT_HOME/agent.yaml` 或 `.env` 已存在
- **THEN** script 不覆盖已有文件
- **AND** 保留 operator 现有内容

#### Scenario: Skip config flag
- **WHEN** operator 运行 install script with `--skip-config`
- **THEN** script 不拷贝任何模板（既不 seed agent.yaml 也不 seed .env）
