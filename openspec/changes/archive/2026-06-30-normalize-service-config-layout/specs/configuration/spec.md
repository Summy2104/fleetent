## MODIFIED Requirements

### Requirement: Local configuration initialization

系统 SHALL 提供 `fleetent platform init-config` 作为 Platform home 配置初始化入口。init-config SHALL 从**打包进 wheel 的 package data**(`importlib.resources`)读取 example 模板,SHALL NOT 依赖当前工作目录(`Path.cwd()`)——使 `uv tool install` 装好的环境也能正确生成配置。

#### Scenario: Init config creates local Platform files
- **WHEN** operator 运行 `fleetent platform init-config`
- **THEN** 系统从 `.env.example` 创建 `.env`
- **AND** 从 `platform.yaml.example` 创建 `platform.yaml`
- **AND** 创建 `data/`、`data/logs/`、`data/diagnostics/` 和 `secrets/`

#### Scenario: Init config reads templates from packaged resources
- **WHEN** 在非仓库目录(无 `examples/`/无根 `*.example`)运行 `fleetent platform init-config` 或 `fleetent node init-config`
- **THEN** init-config 从打包资源读取模板并成功生成配置
- **AND** 不因 `Path.cwd()` 无模板而失败

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

### Requirement: Canonical templates avoid ambiguous agent paths

Repository examples SHALL live beside the runtime files they template,统一平铺在仓库根目录。The
repository SHALL provide these canonical config examples(全部平铺在仓库根):

- `.env.example`
- `platform.yaml.example`
- `agent.yaml.example`
- `agent.env.example`
- `node.env.example`
- `kb-service.yaml.example`
- `kb-service.env.example`

The repository SHALL NOT use `config/` 或 `examples/<role>/` 作为 deployment template namespace——所有 canonical example 平铺在仓库根。这些 example SHALL 被纳入 wheel package data,使 init-config 经打包资源读取(不依赖 cwd)。canonical example SHALL 为完整参考(非最小骨架),覆盖其运行时文件所有当前支持的非密字段与配对 env 引用。

#### Scenario: Canonical examples are flat at repo root
- **WHEN** 查看仓库配置模板
- **THEN** `.env.example` / `platform.yaml.example` / `agent.yaml.example` / `agent.env.example` / `node.env.example` / `kb-service.yaml.example` / `kb-service.env.example` 均平铺在仓库根
- **AND** 不需要通过 `config/` 或 `examples/<role>/` 子目录理解配置

#### Scenario: No subdirectory template namespace
- **WHEN** 查看仓库根目录
- **THEN** `config/` 不存在
- **AND** 不存在 `examples/kb-service/`(kb-service example 平铺在根)

#### Scenario: Default Agent examples live at repo root
- **WHEN** 查看默认 Agent 模板
- **THEN** 存在根目录 `agent.yaml.example`
- **AND** 存在根目录 `agent.env.example`
- **AND** 不存在 `agents/default/` 目录

#### Scenario: Examples are packaged for installed environments
- **WHEN** 从 wheel 安装后(无仓库 checkout)运行 init-config
- **THEN** canonical example 经 package data 可读,init-config 成功
