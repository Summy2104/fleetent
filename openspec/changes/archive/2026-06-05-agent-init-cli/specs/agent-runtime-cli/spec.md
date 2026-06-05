## ADDED Requirements

### Requirement: Scaffold an agent home via `fleetent agent init`
`fleetent agent init <agent-id>` SHALL scaffold a self-contained, runnable agent home from a built-in template, with zero platform/DB dependency. The generated home SHALL be directly runnable by `fleetent agent run <agent-id>`.

#### Scenario: Init creates a runnable home
- **WHEN** operator 运行 `fleetent agent init my-bot`
- **THEN** 在 `FLEETENT_HOME/my-bot/` 下创建 `agent.yaml`
- **AND** `agent.yaml` 的 `name` 字段等于 `my-bot`（满足 `agent run` 的目录名==name 校验）
- **AND** 生成的 `agent.yaml` 能被运行时加载器解析通过

#### Scenario: Env scaffold lists referenced env-var names
- **WHEN** init 写出 home
- **THEN** 创建 `FLEETENT_HOME/my-bot/.env`，列出生成 agent 引用的 env-var 名（含 `ANTHROPIC_API_KEY`），值为空待填
- **AND** 不写入任何真实密钥

#### Scenario: Home override
- **WHEN** operator 运行 `fleetent agent init my-bot --home /opt/agents/my-bot`
- **THEN** 在该路径而非 `FLEETENT_HOME/my-bot` 下 scaffold

#### Scenario: Refuses to overwrite without --force
- **WHEN** 目标 `agent.yaml` 已存在且未传 `--force`
- **THEN** 命令报错并以非零退出码退出
- **AND** 不修改已有 `agent.yaml`

#### Scenario: --force overwrites agent.yaml but preserves .env
- **WHEN** 目标已存在且传 `--force`
- **THEN** 覆盖 `agent.yaml`
- **AND** 已存在的 `.env` 不被覆盖

#### Scenario: No platform or database dependency
- **WHEN** init 运行
- **THEN** 不访问平台服务或数据库（纯本地文件 scaffold）
