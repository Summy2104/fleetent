# agent-runtime-cli Specification

## Purpose
The standalone agent runtime: `fleetent agent run` boots one agent home as a
self-contained process (loop + bound IM + optional HTTP/ws), and the one-shot CLI applies
the deployed home agent — both independent of any platform service. Created by archiving
change agent-runtime-cli.
## Requirements
### Requirement: Standalone agent runtime via `fleetent agent run`

The `fleetent` command SHALL provide `agent run <agent-id> [--port N]` that boots a
single agent as a self-contained foreground process: it resolves the agent home at
`FLEETENT_HOME/<agent-id>/` (`agent.yaml` + `.env` + `data/` + local access), loads it,
runs the agent loop, and starts that agent's IM connectors. The process SHALL run
without any platform service.

#### Scenario: Boot one agent from its home

- **WHEN** `fleetent agent run support` is invoked and `FLEETENT_HOME/support/agent.yaml`
  exists
- **THEN** the process loads that home's agent and starts its IM connectors, with no
  platform server required

#### Scenario: IM is always bound to the agent

- **WHEN** the agent home declares `connectors.slack`
- **THEN** the running agent process maintains that Slack connection; IM is not available
  outside an agent process

### Requirement: HTTP is opt-in via `--port`

The agent runtime SHALL serve HTTP `/chat` and `/ws` (TUI) only when `--port` is given;
without `--port` it runs IM/CLI/TUI-only with no HTTP listener.

#### Scenario: HTTP served with --port

- **WHEN** `fleetent agent run support --port 8770` is invoked
- **THEN** `/chat` and `/ws` are served on 8770 for the `support` agent

#### Scenario: No HTTP without --port

- **WHEN** `fleetent agent run support` is invoked with no `--port`
- **THEN** no HTTP listener is opened; the agent serves IM (and local CLI/TUI) only

### Requirement: One-shot CLI applies the deployed agent

`fleetent "<prompt>"` SHALL apply the resolved home/default agent's `system_prompt`,
`allowed_tools`, and `allowed_skills` for the run, instead of a generic default.

#### Scenario: One-shot runs as the deployed agent

- **WHEN** a home agent defines a distinctive `system_prompt` and `allowed_tools` and
  `fleetent "你好"` is run
- **THEN** the run uses that agent's system prompt and tool allowlist, not the generic
  default

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

