# node-supervisor Specification

## Purpose
TBD - created by archiving change node-supervisor. Update Purpose after archive.
## Requirements
### Requirement: fleetent node start 守护与配置

系统 SHALL 提供 `fleetent node start`（`fleetent` 的 `node start` 子命令），作为跑在每个 agent host 上的长驻守护。它 SHALL 从配置读取：platform 基址、本 node 的 node-id、node service key（`ma-<hex>`）、`FLEETENT_HOME`、reconcile 轮询间隔。配置 SHALL 优先从 `$FLEETENT_HOME/node/.env` 加载（经 `load_dotenv(override=False)`：文件不存在则静默跳过；进程已有的环境变量优先于文件值），其余经环境变量（`FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` / `FLEETENT_NODE_INTERVAL_SECONDS`）。`FLEETENT_HOME` SHALL 经进程环境提供（它是定位 node `.env` 的前提，不可经该 `.env` 设置）。`fleetent node start` SHALL 作为 platform HTTP API 的客户端运行，SHALL NOT `import fleetent.platform.*`，SHALL NOT `import` agent runtime 内部实现（仅经 subprocess 调用 agent CLI）。

#### Scenario: 守护启动并周期 reconcile

- **WHEN** `fleetent node start` 以有效配置启动
- **THEN** 它进入循环：按间隔拉取期望态 → reconcile → 上报实际态

#### Scenario: 从 node .env 加载配置

- **WHEN** `$FLEETENT_HOME/node/.env` 含 `FLEETENT_NODE_PLATFORM_URL` / `FLEETENT_NODE_ID` / `FLEETENT_NODE_SERVICE_KEY` 且这些变量未在进程环境中设置
- **THEN** `fleetent node start` 从该文件读取并成功启动

#### Scenario: 进程环境优先于 node .env

- **WHEN** 某变量同时存在于进程环境与 `$FLEETENT_HOME/node/.env`
- **THEN** 采用进程环境的值（`override=False`）

#### Scenario: node .env 缺失则回退进程环境

- **WHEN** `$FLEETENT_HOME/node/.env` 不存在
- **THEN** 加载步骤静默跳过，配置仅来自进程环境

#### Scenario: 缺失必需配置则拒绝启动

- **WHEN** 文件与进程环境均未提供 node-id 或 service key 或 platform 基址
- **THEN** `fleetent node start` 报错退出，不进入循环

### Requirement: 拉取分区期望态（platform-api provider + 本地缓存）

`fleetent node start` SHALL 经 `GET /nodes/{node-id}/desired-state` 拉取期望态（携带 `Authorization: Bearer <node service key>`），解析响应 `{node_id, agents:[{agent_id, name, config}]}`。期望态来源 SHALL 经可插拔 provider（v1 为 platform-api）。每次成功拉取 SHALL 缓存到 node 本地；当 platform 暂不可达时，SHALL 用最近一次缓存继续 reconcile（避免 platform 短暂下线即停摆）。

#### Scenario: 正常拉取并解析

- **WHEN** platform 返回两个 enabled agent
- **THEN** node 得到两个 (agent_id, name, config) 条目，作为本轮期望集

#### Scenario: platform 不可达时回落缓存

- **WHEN** 拉取失败但存在上一次缓存
- **THEN** node 用缓存的期望集继续 reconcile，并记录拉取失败；缓存缺失时本轮跳过且不误停在跑的 agent

### Requirement: 幂等 reconcile（期望↔实际）

`fleetent node start` SHALL 把期望集调谐成本地真实进程，幂等：

- 期望含某 agent ∧ 其本地未在跑 → 写下发 `config` 到本地 agent home，再经进程后端拉起。
- 某 agent 本地在跑 ∧ 不在期望集（被 disable/archive/unpin）→ 经进程后端优雅停。
- **实际态真相取本地 PID 文件 + 探活**，不依赖守护自身内存——故 `fleetent node start` 重启后 SHALL re-adopt 仍在跑的 agent（不重复拉起、不误杀）。
- 某 agent 期望在跑但进程已死（崩溃）→ 下一轮重新拉起。

#### Scenario: 拉起缺失的期望 agent

- **WHEN** 期望含 agentA 且本地无其存活进程
- **THEN** node 写 agentA 的 config 到本地 home 并拉起其进程

#### Scenario: 停掉不再期望的 agent

- **WHEN** agentB 本地在跑但不在本轮期望集
- **THEN** node 优雅停 agentB

#### Scenario: 守护重启后 re-adopt

- **WHEN** `fleetent node start` 重启，本地 PID 文件显示 agentA 仍存活且仍在期望集
- **THEN** node 不重复拉起 agentA、不杀它

#### Scenario: 崩溃的期望 agent 被重拉

- **WHEN** agentA 在期望集但其 PID 文件对应进程已不存活
- **THEN** 下一轮 reconcile 重新拉起 agentA

### Requirement: config-hash 漂移触发优雅重启

`fleetent node start` SHALL 记录每个在跑 agent 已应用配置的 hash；当期望态下发的 `config` hash 与在跑的不一致时，SHALL 优雅停后用新配置重拉（agent 进程 home-driven、boot 时读配置，无热重载）。

#### Scenario: 配置变更后重启

- **WHEN** agentA 在跑，期望态返回的 config hash 与已应用的不同
- **THEN** node 优雅停 agentA、写新 config、重新拉起

#### Scenario: 配置未变不重启

- **WHEN** 期望态 config hash 与在跑的一致
- **THEN** node 不动该 agent

### Requirement: 上报实际态

`fleetent node start` SHALL 每轮经 `POST /nodes/{node-id}/status` 上报本地各 agent 的实际态 `{agents:[{agent_id, phase, pid?, health?, detail?}]}` 与心跳。上报为只读投影，不影响本地控制决策（控制真相在 PID 文件）。

#### Scenario: 上报在跑 agent

- **WHEN** 本轮 agentA 在跑(pid=123)
- **THEN** node POST 上报 agentA phase=running、pid=123

#### Scenario: 上报失败不影响本地 reconcile

- **WHEN** 上报请求失败
- **THEN** node 记录失败但本地进程不受影响，下轮重试

### Requirement: Node reports per-agent health

When the node supervisor reports actual state, it SHALL determine and include each running agent's `health` by probing the agent's loopback `/health` endpoint (using the agent's recorded gateway port): a `200` response maps to `healthy`, any non-200 / unreachable maps to `unhealthy`; an agent without a gateway port falls back to process liveness (`is_alive` → `healthy`). The probe SHALL be bulkheaded — a single agent's probe failure marks that agent `unhealthy` and MUST NOT affect other agents' reporting or kill the reconcile loop.

#### Scenario: Healthy agent reported healthy

- **WHEN** a running agent's loopback `/health` returns 200
- **THEN** the status report for that agent includes `health = "healthy"`, persisted to `node_agent_status.health`

#### Scenario: Unresponsive agent reported unhealthy

- **WHEN** a running agent's loopback `/health` is unreachable or returns non-200
- **THEN** the report includes `health = "unhealthy"`, and the reconcile loop and other agents' reporting are unaffected

#### Scenario: Probe failure is bulkheaded

- **WHEN** probing one agent raises or times out
- **THEN** that agent is reported `unhealthy`, the exception does not propagate, and the loop continues

### Requirement: Materialize 时 scaffold agent .env / TUI token

`fleetent node start` 在 reconcile 把某个期望 agent 的 home materialize（写 `agent.yaml`）时，SHALL 同时写出一个**完整的 `.env`**（文件权限 `0600`），作为该 agent 所有运行期 env 的单一真相：

- SHALL 列出 `agent.yaml` 引用到的**全部** `*_env` 名——口径为对 agent 定义做 `flatten` 全字段扫描（与平台 `materialize` 同一收集器），**不得**用手枚举子集（消除漏 `embedding`/`rerank`/`telegram`/各 `*_env` 的旧不一致）。
- 对每个名，SHALL 写入其真实值：来自本轮 desired-state 下发的 `secrets`（managed），或既有 operator 值（standalone / operator 手填）。下发 / 已有值缺失的名 SHALL 以空值占位写出（仍可见、可补），node 实现 SHALL 记录"被引用但无值"的名以便排障。
- SHALL 含一个有效的 `FLEETENT_TUI_TOKEN`（`ma-<64 hex>`）：缺则生成、已存在则原样保留（MUST NOT 轮换在跑 agent 的既有 token）。
- 真实 secret 值由此**写入 `.env`**（env-only，见 `node-secret-injection`），不再经进程 env 注入。

该 token 仍是 forwarder（`/forward/agents/{name}/chat`）与 IM-edge 注入 agent loopback `/chat` 的 `Authorization: Bearer` 凭据。

#### Scenario: 新 materialize 的 agent 获得完整 .env

- **WHEN** node reconcile materialize 一个 home 此前不存在 `.env` 的期望 agent
- **THEN** 该 home 出现 `0600` 的 `.env`，含 `agent.yaml` 引用到的全部 `*_env` 名 + `FLEETENT_TUI_TOKEN`
- **AND** 凡本轮 desired-state 下发了值的名，`.env` 中为真实值（非空占位）
- **AND** 经 forwarder `/forward/agents/{name}/chat` 触达该 agent 不再返回 503 `has no env scaffold`

#### Scenario: env 名收集为统一 flatten 口径

- **WHEN** agent 配置同时引用 model `api_key_env`、`embedding.api_key_env`、`rerank.api_key_env`、`telegram.bot_token_env`
- **THEN** materialize 出的 `.env` SHALL 同时列出这四者（flatten 全字段），node 与平台两条路径产物一致

#### Scenario: TUI token 幂等保留

- **WHEN** node reconcile materialize 一个 `.env` 已含 `FLEETENT_TUI_TOKEN=ma-...` 的 agent
- **THEN** 该 `FLEETENT_TUI_TOKEN` 值保持不变，node MUST NOT 因 materialize 而轮换或清空它

### Requirement: 停用 agent 时擦除其 .env

`fleetent node start` 在某 agent 不再属于本 node 期望集（`unpin` / `disable` / 删除）而被停掉进程时，SHALL 擦除该 agent home 的 `.env`，不为已停用 agent 在盘上保留明文 secret。该擦除 SHALL 舱壁化（单 agent 擦除失败只记日志，不影响其它 agent 的 reconcile）。

#### Scenario: 停用即擦 .env

- **WHEN** agentA 从本 node unpin（或 disable / 删除），node 停掉其进程
- **THEN** agentA home 的 `.env` 被擦除，盘上不再留其明文 secret
- **AND** 单个擦除失败只记日志，不改变进程退出码、不波及其它 agent

