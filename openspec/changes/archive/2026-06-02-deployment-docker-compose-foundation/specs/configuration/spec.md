## ADDED Requirements

### Requirement: Local configuration initialization
系统 SHALL 提供 `fleetent admin init-config` 作为本地部署配置初始化入口。

#### Scenario: Init config creates local deployment files
- **WHEN** operator 运行 `fleetent admin init-config`
- **THEN** 系统从 `.env.example` 创建 `.env`
- **AND** 从 `config/settings.yaml.example` 创建 `config/settings.yaml`
- **AND** 从 `config/mcp.servers.yaml.example` 创建 `config/mcp.servers.yaml`
- **AND** 创建 `data/`、`data/logs/`、`data/diagnostics/` 和 `secrets/`

#### Scenario: Init config does not overwrite by default
- **WHEN** 目标文件已经存在
- **AND** operator 未传 `--force`
- **THEN** init-config 跳过该文件
- **AND** 输出说明该文件已存在

#### Scenario: Init config dry run does not write
- **WHEN** operator 运行 `fleetent-admin init-config --dry-run`
- **THEN** 系统输出将创建、跳过或覆盖的路径
- **AND** 不写入文件系统

#### Scenario: Init config force overwrites generated files
- **WHEN** operator 运行 `fleetent-admin init-config --force`
- **THEN** 系统覆盖 `.env`、`config/settings.yaml` 和 `config/mcp.servers.yaml`
- **AND** 不删除未知文件
- **AND** 不生成任何真实 secret 文件

### Requirement: Env and secrets files stay out of git
本地 `.env` 和 `secrets/` SHALL 不进入版本控制；项目 SHALL only provide safe examples.

#### Scenario: Env example is versioned
- **WHEN** maintainer 查看仓库
- **THEN** `.env.example` 存在
- **AND** `.env` 被 git ignore
- **AND** `.env.example` 不包含真实 token、API key、password 或客户数据

#### Scenario: Secrets directory is ignored
- **WHEN** maintainer 查看仓库
- **THEN** `secrets/` 被 git ignore
- **AND** 仓库只提交 secrets 说明文档

#### Scenario: Secrets are deployment-level and flat
- **WHEN** operator 查看 secrets 说明文档
- **THEN** 文档说明 `secrets/` 目录平铺
- **AND** 示例文件名不包含 scope
- **AND** scope 由 connector config 或未来数据库配置表达

### Requirement: Credential references use container secrets path in examples
配置样例 SHALL 使用 Docker Compose mount 后的 `/app/secrets` 路径展示 file credential reference。

#### Scenario: Google Drive credential ref uses app secrets path
- **WHEN** operator 查看 `config/settings.yaml.example`
- **THEN** Google Drive 示例 `credential_ref` 使用 `file:///app/secrets/google-drive-token.json`

#### Scenario: Credential ref does not encode scope in filename
- **WHEN** operator 查看配置样例和 secrets 文档
- **THEN** secret 文件名不使用 `eng`、`product` 或类似 connector scope 作为命名要求
