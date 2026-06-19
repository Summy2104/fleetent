> ⏳ **骨架（skeleton）**：本 change 仅 `proposal.md`。`specs/` 与 `tasks.md` 留待 JIT。
> 属**编排序列 C3/5**（最大一块）。依赖：[`node-desired-state-api`]（契约）。下游：[`node-secret-delivery`]（紧跟/可合并）、[`retire-inmemory-controller`]（替代到位后才拆旧）。

## Why

契约（C2）有了，需要**消费它的那一端**：一个跑在每个 agent host 上的 node 守护进程，把 platform 的期望态调谐成本地真实进程。这是 kubelet 式模型的 node 侧——它让"platform 独立 + N 个 node"真正跑起来，且**真相落在 node 的 PID 文件**而非 platform 内存（platform 重启可 re-adopt、agent 崩溃下个 tick 重拉）。

## What Changes

- **新部署件 `fleetent node start`**（新 console-script + 顶层 `node/` 包）：长驻守护，每个 agent host 一个。
- **reconcile 循环**：拉 C2 的分区期望态 → 与**本地实际态**（`<home>/.fleetent.pid` + `os.kill` 探活）比对 → `enabled∧死`→`fleetent agent run` 拉起；`disabled/archived∧活`→优雅停（复用 agent 既有 SIGUSR1→SIGTERM→SIGKILL）。幂等。
- **进程后端可插拔（仿 sandbox backend）**：v1 落 **local**（`subprocess.Popen` + PID 文件 + 信号）；systemd 后端列 roadmap。
- **配置/secret 来源 provider 可插拔**：v1 **platform-api provider**；node **本地缓存**最后一次期望态/配置（兜 platform 短暂下线仍能跑/重启 agent，**补掉 platform 单点**）。
- **spawn 前准备 home**：把下发的 materialized 配置写本地 agent home，再 `fleetent agent run`。
- **config-hash 漂移→优雅重启**（仿 sandbox config_hash）：跑着的进程配置 hash 与最新不符 → drain+重拉。
- 不做：secret 注入（C4）；systemd/k8s 后端、Consul/etcd/Vault provider、failover/调度（roadmap）。

## Capabilities

### New Capabilities
- `node-supervisor`: `fleetent node start` 守护——配置(node-id/token/platform-url)、拉取(platform-api provider + 本地缓存)、幂等 reconcile(期望↔实际、PID 真相、re-adopt、崩溃重拉、config-hash 漂移重启)、实际态上报。
- `node-process-backend`: 可插拔进程后端接口 + local 实现（spawn `fleetent agent run`、stop via `fleetent agent stop`、liveness via PID 文件 + os.kill）。

### Modified Capabilities
- `agent-runtime-cli`: **新增 `fleetent agent stop <agent-id>`**（薄包既有 `_stop_running` drain 协议 SIGUSR1→SIGTERM→SIGKILL），供 node 经 subprocess 优雅停 agent——drain 逻辑单一真相源留在 runtime，node 不重复实现、不 import runtime 内部。

> 注：本 proposal 由 skeleton 细化（C2 `node-desired-state-api` 已 apply 落 main，迁移 097）。对着 C2 真实契约写：
> GET `/nodes/{id}/desired-state` → `{node_id, agents:[{agent_id,name,config}]}`；
> POST `/nodes/{id}/status` ← `{agents:[{agent_id,phase,pid?,health?,detail?}]}`；Bearer node-key + URL 自限。

## Impact

**owning package**：**新顶层 `node/` 包** + 打包（新 `fleetent node start` 入口）。

**边界（关键）**：`node/` **作为 platform 的 HTTP client** 消费 C2 API，**MUST NOT `import fleetent.platform.*`**；拉起 agent 走 **subprocess（`fleetent agent run`）**，**不 import agent runtime 内部**。故 `node/` 既不依赖 platform 也不依赖 runtime 内部实现——纯"HTTP 客户端 + 子进程编排"，边界极干净，不违反 agent↔platform 解耦铁律。

**public API surface（新增）**：`fleetent node start` CLI；`node/` 的 reconcile / backend / provider 接口（供后续 systemd/Vault 等后端实现）。

**owned tables**：无（node 不写管理库；本地缓存为 node 本地文件/内存，非管理表）。

**config namespace**：`fleetent node start` 运行配置（platform URL、node-id、service-key、轮询/缓存参数、`FLEETENT_HOME`）。

**cross-module dependencies**：HTTP→platform C2 API；subprocess→`fleetent agent run`；读本地 PID 文件。无 Python import 跨边界。

**migration / shim plan**：无管理库 schema、无迁移、无 shim。

**不碰**：`data-model.md`、主 specs（delta 写 change 内）。
