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

The agent process SHALL handle SIGUSR1 as a graceful drain signal with the following
ordered shutdown chain: stop accepting new work (IM supervisors and the cron scheduler
stop first), wait for all in-flight `loop.run()` calls to complete (up to the drain
timeout), **then release all MCP session hosts via `aclose_all()`**, then exit cleanly.
The drain timeout SHALL be configurable via `FLEETENT_RESTART_DRAIN_TIMEOUT` (seconds,
default 30). Every step of the shutdown chain SHALL be **contained**: wrapped with its
own exception handling and a bounded timeout, so a failing or hanging component is
logged and skipped while the remaining steps still run. A teardown error in any
component MUST NOT propagate to other components and MUST NOT change the process exit
code: the graceful drain path SHALL exit with code 0.

#### Scenario: Drain completes before timeout

- **WHEN** SIGUSR1 is received and all in-flight requests complete within drain_timeout
- **THEN** the process stops the IM supervisors and scheduler, waits for the active run
  count to reach zero, releases MCP session hosts, and exits with code 0

#### Scenario: Drain timeout exceeded

- **WHEN** SIGUSR1 is received and active runs do not complete within drain_timeout
- **THEN** the process logs the remaining run count, still releases MCP session hosts,
  and exits anyway (allowing SIGTERM from the restart command)
- **AND** in-flight requests are interrupted

#### Scenario: Teardown error is contained

- **WHEN** any shutdown step (IM supervisor stop, scheduler shutdown, MCP host close)
  raises or hangs past its step timeout
- **THEN** the failure is logged as a warning, the remaining shutdown steps still
  execute, and the process still exits with code 0

#### Scenario: Graceful restart leaves no crash trace

- **WHEN** `fleetent agent restart` triggers SIGUSR1 on a healthy agent
- **THEN** the old process exits with code 0 and no traceback is written to the journal

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

### Requirement: `fleetent agent stop` 优雅停一个本地 agent

`fleetent` CLI SHALL 提供 `agent stop <agent-id>`，对该 agent home 的运行进程执行优雅停机：复用既有 drain 协议（读 `<home>/.fleetent.pid` → SIGUSR1 排干 → 超时 SIGTERM → 再超时 SIGKILL），与 `agent restart` 的停机阶段同一实现（单一真相源）。无 pid 文件或进程已退出时 SHALL 静默成功（幂等）。该命令使 node supervisor 可经 subprocess 优雅停 agent，而无需在 node 侧重复信号逻辑、无需 import runtime 内部。

#### Scenario: 停一个在跑的 agent

- **WHEN** `fleetent agent stop support` 且其进程在跑
- **THEN** 进程经 SIGUSR1 drain 优雅退出（超时回退 SIGTERM/SIGKILL），pid 文件清理

#### Scenario: 停一个已不在跑的 agent 幂等成功

- **WHEN** `fleetent agent stop support` 但无 pid 文件或进程已退出
- **THEN** 命令静默成功，不报错

### Requirement: B 类冗余 CLI 命令已移除

B 类冗余 CLI 命令 SHALL NOT 再通过 `fleetent admin` 暴露；运维与控制面 SHALL 改走对应 HTTP API。

**Reason**: 以下命令均已有等价 HTTP API——其中 6 条的 API 由前置 change `complete-admin-api-coverage` 补齐——CLI 入口冗余。

**Migration**:
- `create-user` → `POST /admin/service-principals`（建服务账号即发 key）
- `rotate-key` → `POST /admin/users/{user_id}/rotate-key`
- `set-default-agent` → `PUT /admin/agents/{name}/default` / `DELETE /admin/agents/default`
- `observability traces/usage/performance` → `GET /admin/observability/{traces,usage,performance}`
- `list-users` → `GET /admin/users`；`block-user`（已是 no-op stub）→ `POST /admin/im-users/{id}/block`
- `update-agent`/`list-agent-versions`/`activate-agent-version`/`show-agent` → `/admin/agents/{name}/*`
- `assign-user`/`unassign-user` → `POST|DELETE /admin/agents/{name}/bindings/users/{user_id}`
- `kb connectors list/check/status/sync` → `/admin/kb/connectors/*`

已移除（共 18 条）：`create-user`、`list-users`、`rotate-key`、`block-user`、`update-agent`、`list-agent-versions`、`activate-agent-version`、`show-agent`、`assign-user`、`unassign-user`、`set-default-agent`、`kb connectors list`、`kb connectors check`、`kb connectors status`、`kb connectors sync`、`observability traces`、`observability usage`、`observability performance`。

#### Scenario: 已移除命令不再可用

- **WHEN** 用户运行 `fleetent admin create-user`（或其他已移除命令）
- **THEN** argparse 报 `invalid choice` 错误（命令不存在）

### Requirement: `fleetent admin` 子命令组

`fleetent` 命令 SHALL 提供 `admin` 子命令组，作为平台管理 CLI 的**唯一**入口（旧 `fleetent-admin` console script 已移除）。`fleetent admin <cmd>` SHALL 复用 `platform.admin_cli` 实现；`fleetent admin --help` 的 usage 行 SHALL 显示 `fleetent admin`。admin 子命令的 import SHALL 懒加载，不在 `fleetent agent run` 启动路径触发。

#### Scenario: admin 子命令可用

- **WHEN** 用户运行 `fleetent admin list-tenants`（保留命令）
- **THEN** 命令执行，输出与底层 `platform.admin_cli` 实现一致

#### Scenario: 旧 fleetent-admin 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-admin` 入口；管理 CLI 仅经 `fleetent admin` 暴露

#### Scenario: agent run 不加载 admin 代码

- **WHEN** 调度到 `fleetent agent run` 分支（serve 被 mock，sys.modules 先清除 `fleetent.platform.admin_cli`）
- **THEN** `fleetent.platform.admin_cli` 不在 `sys.modules`

### Requirement: `fleetent node start` 子命令

`fleetent` 命令 SHALL 提供 `node start`，启动 node supervisor，作为其**唯一**入口（旧 `fleetent-node` console script 已移除）。node 配置经 `FLEETENT_NODE_*` 环境变量，无命令行参数透传。

#### Scenario: node start 启动 supervisor

- **WHEN** 用户运行 `fleetent node start`
- **THEN** node supervisor 启动，行为与旧 `fleetent-node` 相同

#### Scenario: 旧 fleetent-node 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-node` 入口；node supervisor 仅经 `fleetent node start` 启动

