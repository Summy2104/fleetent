## MODIFIED Requirements

### Requirement: Standalone agent runtime via `fleetent agent run`

The `fleetent` command SHALL provide `agent run <agent-id> [--port N]` that boots a
single agent as a self-contained foreground process: it resolves the agent home at
`FLEETENT_HOME/agents/<agent-id>/` (`agent.yaml` + `.env` + `data/` + local access), loads it,
runs the agent loop, and starts that agent's IM connectors. The process SHALL run
without any platform service.

Before scanning `agent.yaml`, `boot()` SHALL load `<home_dir>/.env` into the process
`os.environ` using `load_dotenv(override=False)`. If the file does not exist the step
SHALL be silently skipped. Variables already present in the process environment (injected
by systemd `EnvironmentFile`, Docker `--env-file`, or shell `export`) SHALL take
precedence over values in `.env`.

#### Scenario: Boot one agent from its home
- **WHEN** `fleetent agent run support` is invoked and `FLEETENT_HOME/agents/support/agent.yaml`
  exists
- **THEN** the process loads that home's agent and starts its IM connectors, with no
  platform server required

#### Scenario: .env is loaded before agent.yaml is scanned
- **WHEN** `<home_dir>/.env` exists and contains `SLACK_BOT_TOKEN=xoxb-abc`
- **THEN** `os.environ["SLACK_BOT_TOKEN"]` equals `xoxb-abc` by the time `scan_home()` runs
- **AND** downstream consumers (`slack_supervisor`, `model/resolver`) read the correct value

#### Scenario: Old flat agent home is not used
- **WHEN** `FLEETENT_HOME/support/agent.yaml` exists
- **AND** `FLEETENT_HOME/agents/support/agent.yaml` does not exist
- **THEN** `fleetent agent run support` fails rather than loading the old flat path

### Requirement: Scaffold an agent home via `fleetent agent init`

`fleetent agent init <agent-id>` SHALL scaffold a self-contained, runnable agent home under
`FLEETENT_HOME/agents/<agent-id>/` from a built-in template, with zero platform/DB dependency.
The generated home SHALL be directly runnable by `fleetent agent run <agent-id>`.

#### Scenario: Init creates a runnable home
- **WHEN** operator 运行 `fleetent agent init my-bot`
- **THEN** 在 `FLEETENT_HOME/agents/my-bot/` 下创建 `agent.yaml`
- **AND** `agent.yaml` 的 `name` 字段等于 `my-bot`（满足 `agent run` 的目录名==name 校验）
- **AND** 生成的 `agent.yaml` 能被运行时加载器解析通过

#### Scenario: Env scaffold lists referenced env-var names
- **WHEN** init 写出 home
- **THEN** 创建 `FLEETENT_HOME/agents/my-bot/.env`，列出生成 agent 引用的 env-var 名，值为空待填
- **AND** 不写入任何真实密钥

#### Scenario: Home override
- **WHEN** operator 运行 `fleetent agent init my-bot --home /opt/agents/my-bot`
- **THEN** 在该路径而非 `FLEETENT_HOME/agents/my-bot` 下 scaffold
