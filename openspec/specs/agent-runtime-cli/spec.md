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

Before scanning `agent.yaml`, `boot()` SHALL load `<home_dir>/.env` into the process
`os.environ` using `load_dotenv(override=False)`. If the file does not exist the step
SHALL be silently skipped. Variables already present in the process environment (injected
by systemd `EnvironmentFile`, Docker `--env-file`, or shell `export`) SHALL take
precedence over values in `.env`.

#### Scenario: Boot one agent from its home

- **WHEN** `fleetent agent run support` is invoked and `FLEETENT_HOME/support/agent.yaml`
  exists
- **THEN** the process loads that home's agent and starts its IM connectors, with no
  platform server required

#### Scenario: IM is always bound to the agent

- **WHEN** the agent home declares `connectors.slack`
- **THEN** the running agent process maintains that Slack connection; IM is not available
  outside an agent process

#### Scenario: .env is loaded before agent.yaml is scanned

- **WHEN** `<home_dir>/.env` exists and contains `SLACK_BOT_TOKEN=xoxb-abc`
- **THEN** `os.environ["SLACK_BOT_TOKEN"]` equals `xoxb-abc` by the time `scan_home()` runs
- **AND** downstream consumers (`slack_supervisor`, `model/resolver`) read the correct value

#### Scenario: Missing .env is silently skipped

- **WHEN** `<home_dir>/.env` does not exist
- **THEN** `boot()` proceeds normally without error
- **AND** agent startup behaviour is identical to the pre-change state

#### Scenario: Process-level env takes precedence over .env

- **WHEN** `SLACK_BOT_TOKEN=xoxb-injected` is already set in the process environment
- **AND** `<home_dir>/.env` contains `SLACK_BOT_TOKEN=xoxb-from-file`
- **THEN** `os.environ["SLACK_BOT_TOKEN"]` remains `xoxb-injected`
- **AND** the `.env` value is NOT applied

#### Scenario: Multiple agents on the same server have isolated environments

- **WHEN** two `fleetent agent run` processes start concurrently for `agent-a` and `agent-b`
- **AND** each home contains a `.env` with the same variable name but different values
- **THEN** the `agent-a` process sees only `agent-a`'s value
- **AND** the `agent-b` process sees only `agent-b`'s value
- **AND** neither process's `os.environ` is visible to the other

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

### Requirement: Restart running agent via `fleetent agent restart`

The `fleetent` command SHALL provide `agent restart <agent-id> [--port N] [--home PATH]`
that stops the currently running agent process gracefully and boots a fresh one in its place.
The command SHALL send SIGUSR1 to trigger graceful drain, wait up to `drain_timeout` seconds
(default 30s) for in-flight requests to complete, then fall back to SIGTERM (5s) and finally
SIGKILL if the process does not exit.

#### Scenario: Restart a running agent

- **WHEN** `fleetent agent restart support` is invoked and `<home>/.fleetent.pid` contains
  a live PID
- **THEN** SIGUSR1 is sent to the running process
- **AND** the running process stops accepting new IM messages and waits for in-flight requests
- **AND** after the old process exits, a new agent process boots and runs in the foreground

#### Scenario: Restart with no running process is idempotent

- **WHEN** `fleetent agent restart support` is invoked and no `.fleetent.pid` exists (or
  the recorded process is already gone)
- **THEN** the command silently skips the kill step and boots the agent normally

#### Scenario: SIGTERM fallback after drain timeout

- **WHEN** in-flight requests do not complete within `drain_timeout` seconds after SIGUSR1
- **THEN** SIGTERM is sent to force-terminate the process
- **AND** if the process does not exit within 5 more seconds, SIGKILL is sent

### Requirement: `serve()` maintains a PID file

`serve()` SHALL write the current process ID to `<home_dir>/.fleetent.pid` before
booting the agent, and SHALL delete the file on exit (clean or crash).

#### Scenario: PID file exists while agent is running

- **WHEN** `fleetent agent run support` is executing
- **THEN** `<home>/.fleetent.pid` exists and contains the integer process ID

#### Scenario: PID file removed on shutdown

- **WHEN** the `fleetent agent run` process exits (normally or via signal)
- **THEN** `<home>/.fleetent.pid` no longer exists

### Requirement: Graceful drain on SIGUSR1

The agent process SHALL handle SIGUSR1 as a graceful drain signal: stop accepting new
IM messages, wait for all in-flight `loop.run()` calls to complete, then exit cleanly.
The drain timeout SHALL be configurable via `FLEETENT_RESTART_DRAIN_TIMEOUT` (seconds,
default 30).

#### Scenario: Drain completes before timeout

- **WHEN** SIGUSR1 is received and all in-flight requests complete within drain_timeout
- **THEN** the process stops the IM supervisor, waits for active run count to reach zero,
  then exits normally

#### Scenario: Drain timeout exceeded

- **WHEN** SIGUSR1 is received and active runs do not complete within drain_timeout
- **THEN** the process exits anyway (allowing SIGTERM from the restart command)
- **AND** in-flight requests are interrupted

### Requirement: Active run counter in `loop.run()`

`loop.run()` SHALL maintain a module-level integer counter `_active_runs` that is
incremented on entry and decremented in a `finally` block on exit.

#### Scenario: Counter reflects in-flight runs

- **WHEN** N concurrent calls to `loop.run()` are executing
- **THEN** `loop._active_runs == N`

#### Scenario: Counter decrements on error

- **WHEN** `loop.run()` raises an exception
- **THEN** `_active_runs` is still decremented (via finally)

