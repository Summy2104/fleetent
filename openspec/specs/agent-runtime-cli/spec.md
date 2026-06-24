# agent-runtime-cli Specification

## Purpose
The standalone agent runtime: `fleetent agent run` boots one agent home as a
self-contained process (loop + bound IM + optional HTTP/ws), and the one-shot CLI applies
the deployed home agent — both independent of any platform service. Created by archiving
change agent-runtime-cli.
## Requirements
### Requirement: Standalone agent runtime via `fleetent agent run`

`fleetent agent run <agent-id> [--port N]` SHALL boot a single agent home as a foreground process (loop + bound IM + optional HTTP/ws): by default it resolves `FLEETENT_HOME/tenants/default/agents/<agent-id>/` for standalone/dev compatibility, while managed node invocations SHALL pass the tenant-aware home explicitly. The command loads `agent.yaml` + `.env` + `data/`, runs the agent loop, and brings up that agent's IM connectors. **该命令是 node 拉起 agent 的原语**, 也可被开发者直接运行作 dev/test 调试。

At boot, before runtime infrastructure can write files, the process SHALL redirect every agent-run data sink to `<home>/data/`: sessions, logs, diagnostics, IM approvals, legacy JSONL traces, workspaces, tool spillover, sandbox output spill, agent-side DBs and vector DBs.

#### Scenario: Standalone default tenant run
- **WHEN** developer runs `fleetent agent run support` without `--home`
- **THEN** runtime loads `FLEETENT_HOME/tenants/default/agents/support/agent.yaml`
- **AND** uses `FLEETENT_HOME/tenants/default/agents/support/data/` for runtime data
- **AND** does not write agent runtime files under `FLEETENT_HOME/data/`

#### Scenario: Node passes explicit tenant-aware home
- **WHEN** node starts tenant `acme` agent `support`
- **THEN** it invokes the agent runtime with explicit home `FLEETENT_HOME/tenants/acme/agents/support`
- **AND** runtime does not infer the wrong default tenant home
- **AND** all data sinks bind under `FLEETENT_HOME/tenants/acme/agents/support/data/`

#### Scenario: Explicit home wins
- **WHEN** `fleetent agent run support --home /tmp/custom-home` is used
- **THEN** runtime loads `/tmp/custom-home/agent.yaml`
- **AND** all agent data redirects under `/tmp/custom-home/data`

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

`fleetent agent init <agent-id>` SHALL create `FLEETENT_HOME/tenants/default/agents/<agent-id>/` from a built-in template, with zero platform/DB dependency.

#### Scenario: Init writes default tenant home
- **WHEN** developer runs `fleetent agent init solo`
- **THEN** `FLEETENT_HOME/tenants/default/agents/solo/agent.yaml` exists
- **AND** `.env`, `skills/`, and `data/` are initialized as standalone runtime inputs

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

### Requirement: `fleetent chat` 子命令

`fleetent` 命令 SHALL 提供 `chat` 子命令,作为终端交互客户端的**唯一**入口。`fleetent chat [--url <ws>] [--token <key>]` SHALL 连接 `/ws` 做多轮对话(含斜杠命令),行为等价于改名前的旧 `tui` 子命令 / 更早的 `fleetent-tui`。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发。

#### Scenario: chat 子命令连接 /ws

- **WHEN** 用户运行 `fleetent chat --url ws://localhost:8765/ws --token ma-<key>`
- **THEN** 客户端连接该 `/ws` 并进入多轮对话

#### Scenario: chat help 显示正确 prog 名

- **WHEN** 用户运行 `fleetent chat --help`
- **THEN** usage 行显示 `fleetent chat`

#### Scenario: 旧 fleetent-tui 入口不再存在

- **WHEN** 查看 `pyproject.toml` 的 `[project.scripts]`
- **THEN** 不含 `fleetent-tui` 入口;终端 TUI 仅经 `fleetent chat` 子命令暴露

#### Scenario: chat 沿用 env 默认

- **WHEN** 设置 `FLEETENT_TUI_URL` / `FLEETENT_TOKEN` 后运行 `fleetent chat`
- **THEN** 子命令读取这些环境变量作为 `--url` / `--token` 默认值

### Requirement: `fleetent kb-worker` 子命令

`fleetent` 命令 SHALL 提供 `kb-worker` 子命令,启动 KB ingest 队列的唯一消费者长驻进程。其 import SHALL 懒加载,不在 `fleetent agent run` 启动路径触发(对齐 `fleetent node start` 模式)。worker SHALL NOT `import fleetent.platform.*`。

#### Scenario: kb-worker 启动并消费

- **WHEN** 用户运行 `fleetent kb-worker`
- **THEN** 进程进入循环:claim pending job → 调 ingest 核 → mark done/failed

#### Scenario: agent run 不加载 kb-worker

- **WHEN** 调度到 `fleetent agent run` 分支
- **THEN** `fleetent kb-worker` 的实现模块未被 import(懒加载)

### Requirement: 一次性 CLI 经 Principal 调用 agent loop

`fleetent "<prompt>"` 一次性入口(`run_sync` → `_run`)SHALL 以 `principal=Principal(user_id=..., tenant_id="default")` 调用 `loop.run()`,SHALL NOT 传 `run()` 不接受的 `user_id` 关键字。`run()` / `run_stream()` 的签名(收 `principal`)SHALL 不变。

#### Scenario: 一次性入口真实跑通

- **WHEN** 执行 `fleetent "What is 7*8?"`(LLM 在 `get_client_and_config` 边界打桩)
- **THEN** `_run → run()` 真实执行返回回复,**不抛 `TypeError: run() got an unexpected keyword argument`**

#### Scenario: run 签名不变

- **WHEN** 检视 `loop.run` / `loop.run_stream` 签名
- **THEN** 仍收 `principal: Principal | None`;改的是一次性调用方,不是 run 本身

### Requirement: 真实入口冒烟覆盖一次性路径

集成测试 SHALL 覆盖一次性 `run_sync` 的**真实** `run()` 调用——在 `get_client_and_config` 边界打桩 LLM,**不得 mock `loop.run` 本身**(否则绕过入口签名)。

#### Scenario: 冒烟执行真实 run() 而非 mock 它

- **WHEN** 一次性入口冒烟运行
- **THEN** 它 patch `get_client_and_config`(LLM 边界),`_run → run()` 真实执行;若入口与 run 签名不匹配,测试 SHALL fail

### Requirement: Agent runtime legacy trace path is agent-scoped

While the legacy JSONL trace API remains importable, agent runtime SHALL bind its trace file to `<agent-home>/data/traces.jsonl`, not `FLEETENT_HOME/data/traces.jsonl`.

#### Scenario: Agent run writes legacy trace under agent data
- **WHEN** an agent run records a legacy JSONL trace event
- **THEN** the trace is appended to `<agent-home>/data/traces.jsonl`
- **AND** `FLEETENT_HOME/data/traces.jsonl` is not created

