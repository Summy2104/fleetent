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
- **WHEN** a legacy flat Agent home exists outside `FLEETENT_HOME/agents/<agent-id>/`
- **AND** the canonical `FLEETENT_HOME/agents/support/agent.yaml` does not exist
- **THEN** `fleetent agent run support` fails rather than loading the old flat path

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

### Requirement: Standalone agent 的 skill 索引建自其 home 的 skills 目录

`boot()` SHALL 从 agent 自己 home 的 `skills/` 子目录构建该进程的 skill 索引，使 standalone agent 的 skill catalog 自包含（不依赖进程 CWD 或 `FLEETENT_SKILLS_DIR`）。具体地，`boot()` SHALL 调用 `scan_skills(skills_dir=str(<home_dir>/"skills"))`。

当 `<home_dir>/skills/` 不存在时（如未经平台 materialize 的 `fleetent agent init` home），索引 SHALL 安全回退为仅含 builtin skills（不抛异常）。

#### Scenario: boot 从 home/skills 构建索引

- **WHEN** `<home>/skills/crm-ops/SKILL.md` 存在，`fleetent agent run` 启动该 home
- **THEN** 该进程的 skill 索引包含 "crm-ops"
- **AND** `available_skills_prompt` 渲染的 catalog 含 "crm-ops"（受 allowed_skills/disabled_skills 收窄后）

#### Scenario: home 无 skills 目录时安全

- **WHEN** agent home 没有 `skills/` 子目录，`fleetent agent run` 启动
- **THEN** boot 正常完成，skill 索引仅含 builtin skills，不抛异常

#### Scenario: skill 索引不依赖进程 CWD

- **WHEN** 两个不同 home 的 agent 进程在同一 CWD 启动，各自 home 的 `skills/` 内容不同
- **THEN** 每个进程的 skill 索引反映它自己 home 的 skills，互不影响

### Requirement: agent init generates TUI token in .env

`fleetent agent init` SHALL append `FLEETENT_TUI_TOKEN=ma-<64hex>` to the agent's `.env`
when the `.env` does not already contain a `FLEETENT_TUI_TOKEN` entry. The token is
generated with `secrets.token_hex(32)`.

#### Scenario: .env contains FLEETENT_TUI_TOKEN after init

- **WHEN** `fleetent agent init my-bot` is run
- **THEN** `~/.fleetent/agents/my-bot/.env` SHALL contain a non-empty `FLEETENT_TUI_TOKEN` value
